"""분석 접수. CONTRACTS.md 5절.

입력 세 가지 (모두 같은 job으로 간다)
- POST /api/analyze/pdf : 자기소개서·포트폴리오 PDF (글자만 읽고 파일은 저장하지 않음) ← 화면의 기본 입력
- POST /api/analyze      : {"experiences": [{title,S,T,A,R}], "skills": "..."} 우리 STAR 템플릿으로 쓴 경우
                           또는 {"resume": "..."} 글 붙여 넣기
직군(job_family)은 안 보내면 이력서 스킬로 추정한다("auto").
"""
import io

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..adapters import jobs
from ..agents.supervisor import FAMILIES, FAMILY_LABEL
from ..guards import pii

router = APIRouter(prefix="/api")
MAX_TEXT = 20_000
MAX_PDF = 5 * 1024 * 1024


class ExpIn(BaseModel):
    title: str = Field(default="", max_length=60)
    S: str = Field(default="", max_length=600)
    T: str = Field(default="", max_length=600)
    A: str = Field(default="", max_length=1000)
    R: str = Field(default="", max_length=600)


class AnalyzeIn(BaseModel):
    resume: str | None = Field(default=None, max_length=MAX_TEXT)
    experiences: list[ExpIn] | None = Field(default=None, max_length=8)
    skills: str = Field(default="", max_length=500)
    job_family: str = "auto"
    posting: str | None = Field(default=None, max_length=8000)


@router.get("/families")
def families():
    return [{"id": k, "label": FAMILY_LABEL[k]} for k in FAMILIES]


def _family(f: str | None) -> str:
    f = f or "auto"
    if f != "auto" and f not in FAMILIES:
        raise HTTPException(400, f"job_family는 auto 또는 {list(FAMILIES)} 중 하나")
    return f


def _submit(payload: dict) -> dict:
    job = jobs.create(payload["job_family"])
    jobs.submit(job["job_id"], payload)
    return {"job_id": job["job_id"]}


@router.post("/analyze")
def analyze(body: AnalyzeIn):
    fam = _family(body.job_family)
    posting = body.posting or ""
    if body.experiences:
        exps = []
        for e in body.experiences:
            d = {k: pii.mask(getattr(e, k).strip())[0] for k in ("title", "S", "T", "A", "R")}
            if any(d[k] for k in "STAR"):
                exps.append(d)
        if not exps:
            raise HTTPException(400, "경험 칸을 하나 이상 채워 주세요")
        return _submit({"template": exps, "skills": pii.mask(body.skills)[0], "job_family": fam, "posting": posting,
                        "source": "template"})
    text = (body.resume or "").strip()
    if len(text) < 20:
        raise HTTPException(422, "이력서 내용이 너무 짧습니다 (20자 이상)")
    masked, _ = pii.mask(text)  # 원문은 접수 즉시 정규식으로 가린다. job에는 저장하지 않는다
    return _submit({"resume": masked, "job_family": fam, "posting": posting, "source": "text"})


DOC_LABEL = {"essay": "자기소개서", "portfolio": "포트폴리오", "file": "문서"}
MAX_DOC_CHARS = 10_000   # 문서 하나에서 읽는 글자 수 상한 (Bedrock 입력 비용 상한)


async def _pdf_text(f: UploadFile) -> str:
    if not (f.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 올릴 수 있습니다")
    raw = await f.read()
    if len(raw) > MAX_PDF:
        raise HTTPException(400, "PDF는 5MB 이하만 올릴 수 있습니다 (이미지가 많으면 '최소 크기'로 다시 저장)")
    from pypdf import PdfReader
    try:
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(raw)).pages)
    except Exception:
        raise HTTPException(400, "PDF를 읽지 못했습니다")
    return text.strip()[:MAX_DOC_CHARS]  # 파일은 메모리에서도 바로 버린다


@router.post("/analyze/pdf")
async def analyze_pdf(essay: UploadFile | None = File(None), portfolio: UploadFile | None = File(None),
                      file: UploadFile | None = File(None), job_family: str = Form("auto"), posting: str = Form("")):
    """자기소개서·포트폴리오 PDF(하나 이상). 문서마다 [자기소개서]·[포트폴리오] 머리말을 붙여 한 본문으로 분석한다."""
    fam = _family(job_family)
    docs = {k: f for k, f in (("essay", essay), ("portfolio", portfolio), ("file", file)) if f is not None}
    if not docs:
        raise HTTPException(400, "자기소개서나 포트폴리오 PDF를 하나 이상 올려 주세요")
    parts, total = [], 0
    for k, f in docs.items():
        total += f.size or 0
        if total > MAX_PDF:  # 배포(Lambda 함수 URL)는 요청 하나가 6MB를 넘을 수 없다
            raise HTTPException(400, "PDF는 합쳐서 5MB 이하만 올릴 수 있습니다 (이미지가 많으면 '최소 크기'로 다시 저장)")
        t = await _pdf_text(f)
        if len(t) >= 20:
            parts.append(f"[{DOC_LABEL[k]}]\n{t}")
    if not parts:
        raise HTTPException(400, "PDF에서 글자를 읽지 못했습니다 (스캔 이미지 PDF는 지원하지 않음)")
    masked, _ = pii.mask("\n\n".join(parts))
    return _submit({"resume": masked, "job_family": fam, "posting": posting[:8000], "source": "+".join(docs)})


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "작업이 없거나 만료됨(24시간)")
    return job
