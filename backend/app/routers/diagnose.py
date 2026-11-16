import io

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..data import personas
from ..pipeline import diagnose as dg

router = APIRouter(prefix="/api", tags=["diagnose"])
MAX_RESUME = 20_000


FAMILIES = ["AI·ML 엔지니어", "MLOps·AI 플랫폼", "데이터 엔지니어·분석", "백엔드", "클라우드·인프라·운영", "품질·QA", "게임 개발"]


class CustomIn(BaseModel):
    """목록에 없는 회사 (예: 삼성 개발직). 공고는 붙여 넣고, 실무는 같은 직군 회사들로 추정한다."""
    name: str = Field(..., min_length=1, max_length=40)
    job_family: str
    posting_text: str = Field("", max_length=8000)


class DiagnoseIn(BaseModel):
    company_id: str
    weekly_hours: int = Field(10, ge=1, le=80)
    resume_text: str | None = None
    persona_id: str | None = None
    custom: CustomIn | None = None


@router.get("/personas")
def list_personas():
    return [p for p in personas() if not p.get("test_only")]  # t1~t3은 회귀 테스트 전용


def _run(text: str, company_id: str, hours: int, custom: CustomIn | None = None):
    text = (text or "").strip()
    if not text:
        raise HTTPException(400, "이력서 내용이 비어 있습니다")
    if len(text) > MAX_RESUME:
        raise HTTPException(400, f"이력서는 {MAX_RESUME:,}자 이하로 넣어 주세요")
    if company_id == "custom":
        if custom is None or custom.job_family not in FAMILIES:
            raise HTTPException(400, "직접 입력한 회사는 이름과 직군이 필요합니다")
        if len(custom.posting_text.strip()) < 20:
            raise HTTPException(400, "그 회사 공고(자격요건·우대사항)를 붙여 넣어 주세요")
    try:
        return dg.run(text, company_id, hours, custom=custom.model_dump() if custom else None)
    except KeyError:
        raise HTTPException(404, f"기업 {company_id}를 찾을 수 없습니다")


@router.post("/diagnose")
def diagnose(body: DiagnoseIn):
    text = body.resume_text
    if body.persona_id:
        p = next((p for p in personas() if p["id"] == body.persona_id), None)
        if p is None:
            raise HTTPException(404, "예시 지원자를 찾을 수 없습니다")
        text = p["resume"]
    return _run(text, body.company_id, body.weekly_hours, body.custom)


@router.post("/diagnose/pdf")
async def diagnose_pdf(file: UploadFile = File(...), company_id: str = Form(...), weekly_hours: int = Form(10),
                       custom_name: str = Form(""), custom_family: str = Form(""), custom_posting: str = Form("")):
    custom = CustomIn(name=custom_name[:40] or "직접 입력", job_family=custom_family,
                      posting_text=custom_posting[:8000]) if company_id == "custom" else None
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 올릴 수 있습니다")
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "5MB 이하 PDF만 올릴 수 있습니다")
    from pypdf import PdfReader
    try:
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(raw)).pages)
    except Exception:
        raise HTTPException(400, "PDF에서 글자를 읽지 못했습니다 (스캔 이미지 PDF는 지원하지 않음)")
    res = _run(text, company_id, max(1, min(80, weekly_hours)), custom)
    res["extracted_chars"] = len(text)
    return res
