from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..pipeline import coach

router = APIRouter(prefix="/api", tags=["coach"])


class CoachIn(BaseModel):
    company_id: str = Field(max_length=32)
    question: str = Field(min_length=1, max_length=300)
    # 진단 결과의 스킬 상태 코드만 받는다 (이력서 원문 없음)
    statuses: dict[str, str] = Field(default_factory=dict, max_length=80)


@router.post("/coach")
def ask(body: CoachIn):
    """학습 코치 에이전트: 도구(기업 기준·과정·시장·기업 문서·준비도 계산)를 골라 근거를 모은 뒤 답한다."""
    try:
        return coach.run(body.company_id, body.question.strip(), body.statuses)
    except KeyError:
        raise HTTPException(404, f"기업 {body.company_id}를 찾을 수 없습니다")
