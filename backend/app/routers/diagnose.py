import io

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..data import personas
from ..pipeline import diagnose as dg

router = APIRouter(prefix="/api", tags=["diagnose"])
MAX_RESUME = 20_000


class DiagnoseIn(BaseModel):
    company_id: str
    weekly_hours: int = Field(10, ge=1, le=80)
    resume_text: str | None = None
    persona_id: str | None = None


@router.get("/personas")
def list_personas():
    return personas()


def _run(text: str, company_id: str, hours: int):
    text = (text or "").strip()
    if not text:
        raise HTTPException(400, "이력서 내용이 비어 있습니다")
    if len(text) > MAX_RESUME:
        raise HTTPException(400, f"이력서는 {MAX_RESUME:,}자 이하로 넣어 주세요")
    try:
        return dg.run(text, company_id, hours)
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
    return _run(text, body.company_id, body.weekly_hours)


@router.post("/diagnose/pdf")
async def diagnose_pdf(file: UploadFile = File(...), company_id: str = Form(...), weekly_hours: int = Form(10)):
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
    res = _run(text, company_id, max(1, min(80, weekly_hours)))
    res["extracted_chars"] = len(text)
    return res
