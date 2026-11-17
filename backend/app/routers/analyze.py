"""분석 접수. CONTRACTS.md 5절.

입력 세 가지 (모두 같은 job으로 간다)
- POST /api/analyze/pdf : 이력서 PDF (글자만 읽고 파일은 저장하지 않음)
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


@router.post("/analyze/pdf")
async def analyze_pdf(file: UploadFile = File(...), job_family: str = Form("auto"), posting: str = Form("")):
    fam = _family(job_family)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 올릴 수 있습니다")
    raw = await file.read()
    if len(raw) > MAX_PDF:
        raise HTTPException(400, "5MB 이하 PDF만 올릴 수 있습니다")
    from pypdf import PdfReader
    try:
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(raw)).pages)
    except Exception:
        raise HTTPException(400, "PDF를 읽지 못했습니다")
    del raw  # 파일은 메모리에서도 바로 버린다
    text = text.strip()
    if len(text) < 20:
        raise HTTPException(400, "PDF에서 글자를 읽지 못했습니다 (스캔 이미지 PDF는 지원하지 않음). 템플릿으로 써 주세요")
    masked, _ = pii.mask(text[:MAX_TEXT])
    return _submit({"resume": masked, "job_family": fam, "posting": posting[:8000], "source": "pdf"})


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "작업이 없거나 만료됨(24시간)")
    return job
