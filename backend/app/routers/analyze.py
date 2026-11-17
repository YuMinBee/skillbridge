"""분석 접수. CONTRACTS.md 5절.

입력 세 가지 (모두 같은 job으로 간다)
- POST /api/analyze/docs : 자소서·포트폴리오·CV(PDF·docx)·노션 내보내기(md·txt) + GitHub 주소 ← 화면의 기본 입력
                           (파일은 글자만 읽고 저장하지 않음. GitHub는 공개 README만, job 안에서 읽음)
- POST /api/analyze      : {"experiences": [{title,S,T,A,R}], "skills": "..."} 우리 STAR 템플릿으로 쓴 경우
                           또는 {"resume": "..."} 글 붙여 넣기
직군(job_family)은 안 보내면 이력서 스킬로 추정한다("auto").
"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..adapters import docs, jobs
from ..adapters import github as gh_mod
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


MAX_FILES = 4


async def _read_docs(files: list[UploadFile]) -> list[str]:
    """→ ["[문서 이름] + 본문", ...]. 합쳐서 5MB(Lambda 함수 URL 요청 상한 6MB). 파일은 메모리에서도 바로 버린다."""
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"문서는 {MAX_FILES}개까지 올릴 수 있습니다")
    parts, total = [], 0
    for f in files:
        raw = await f.read()
        total += len(raw)
        if total > MAX_PDF:
            raise HTTPException(400, "문서는 합쳐서 5MB 이하만 올릴 수 있습니다 (이미지가 많으면 '최소 크기'로 다시 저장)")
        try:
            t = docs.text_of(f.filename or "", raw)
        except docs.DocError as e:
            raise HTTPException(400, str(e))
        if len(t) >= 20:
            name = (f.filename or "문서").rsplit(".", 1)[0][:40]
            parts.append(f"[{name}]\n{t}")
    return parts


@router.post("/analyze/docs")
async def analyze_docs(files: list[UploadFile] = File(default=[]), github: str = Form(""),
                       job_family: str = Form("auto"), posting: str = Form("")):
    """자소서·포트폴리오·CV(PDF·docx)·노션 내보내기(md·txt) 여러 개 + GitHub 아이디/레포 주소. 하나 이상."""
    fam = _family(job_family)
    gh = github.strip()
    if gh:
        try:
            gh_mod.parse(gh)
        except gh_mod.GithubError as e:
            raise HTTPException(400, str(e))
    parts = await _read_docs(files)
    if not parts and not gh:
        raise HTTPException(400, "자소서·포트폴리오 문서나 GitHub 주소를 하나 이상 넣어 주세요")
    masked, _ = pii.mask("\n\n".join(parts))
    return _submit({"resume": masked, "github": gh, "job_family": fam, "posting": posting[:8000],
                    "source": "+".join(filter(None, ["docs" if parts else "", "github" if gh else ""]))})


@router.post("/analyze/pdf")
async def analyze_pdf(essay: UploadFile | None = File(None), portfolio: UploadFile | None = File(None),
                      job_family: str = Form("auto"), posting: str = Form("")):
    """(이전 화면 호환) 자기소개서·포트폴리오 PDF."""
    files = [f for f in (essay, portfolio) if f is not None]
    if not files:
        raise HTTPException(400, "자기소개서나 포트폴리오 PDF를 하나 이상 올려 주세요")
    return await analyze_docs(files=files, github="", job_family=job_family, posting=posting)


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "작업이 없거나 만료됨(24시간)")
    return job
