"""POST /api/analyze → job_id, GET /api/jobs/{id}. CONTRACTS.md 5절."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..adapters import jobs
from ..agents.supervisor import FAMILIES, FAMILY_LABEL
from ..guards import pii

router = APIRouter(prefix="/api")


class AnalyzeIn(BaseModel):
    resume: str = Field(min_length=20, max_length=8000)
    job_family: str = "backend"
    posting: str | None = Field(default=None, max_length=8000)


@router.get("/families")
def families():
    return [{"id": k, "label": FAMILY_LABEL[k]} for k in FAMILIES]


@router.post("/analyze")
def analyze(body: AnalyzeIn):
    if body.job_family not in FAMILIES:
        raise HTTPException(400, f"job_family는 {list(FAMILIES)} 중 하나")
    masked, _ = pii.mask(body.resume)  # 원문은 접수 즉시 정규식으로 가린다. job에는 저장하지 않는다
    job = jobs.create(body.job_family)
    jobs.submit(job["job_id"], {"resume": masked, "job_family": body.job_family, "posting": body.posting or ""})
    return {"job_id": job["job_id"]}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "작업이 없거나 만료됨(24시간)")
    return job
