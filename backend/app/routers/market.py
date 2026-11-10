from fastapi import APIRouter, HTTPException, Query

from ..pipeline import market, supply
from ..skills import get_dict

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/market")
def market_summary(region: str = Query("dg"), job: str = Query("ai")):
    if region not in market.REGIONS or job not in market.JOBS:
        raise HTTPException(400, "region은 dg|all, job은 ai|cloud|public|public_it")
    res = market.summary(region, job)
    res["engine"] = _athena_check(region, job, res)
    return res


def _athena_check(region: str, job: str, res: dict) -> dict:
    """배포 환경: 같은 집계를 Athena(S3 curated/)로 다시 내고 로컬 계산과 일치하는지 표시한다."""
    from ..adapters import athena
    if not athena.enabled():
        return {"name": "local"}
    try:
        ar, total, meta = athena.rates(region, job)
    except Exception as e:  # noqa: BLE001 — Athena가 실패해도 화면은 로컬 집계로 뜬다
        return {"name": "local", "error": str(e)[:160]}
    diff = max((abs(ar.get(t["skill_id"], 0) - t["pct"]) for t in res["top"]), default=0)
    return {"name": "athena", "total": total, "match": total == res["n"] and diff < 0.06, **meta}


@router.get("/skills")
def skills(region: str = "dg", job: str = "ai"):
    """스킬 사전 + 시장 언급률 (기업 콘솔의 '역량 추가'용)"""
    if region not in market.REGIONS or job not in market.JOBS:
        raise HTTPException(400, "region은 dg|all, job은 ai|cloud|public|public_it")
    rates = market.rates(region, job)
    out = [{**s, "market_pct": round(rates.get(s["id"], 0), 1)} for s in get_dict().skills.values()]
    out.sort(key=lambda x: (-x["market_pct"], x["name"]))
    return out


@router.get("/supply")
def supply_gap(region: str = Query("dg"), job: str = Query("ai")):
    """스킬별 시장 수요(언급률) × 지역 대면 교육 공급(정원). 수요는 있는데 공급이 0인 '공백' 스킬 표시."""
    if region not in market.REGIONS or job not in market.JOBS:
        raise HTTPException(400, "region은 dg|all, job은 ai|cloud|public|public_it")
    return supply.gap_map(region, job)


@router.get("/digital")
def digital_demand(region: str = Query("dg")):
    """공공기관 전 직무(잡알리오 실공고)의 디지털·AI 역량 요구율 — NCS 분야별, 자격증만으로 묻는 비율."""
    if region not in market.REGIONS:
        raise HTTPException(400, "region은 dg|all")
    from ..pipeline import digital
    return digital.digital_map(region)


@router.get("/quality")
def quality():
    """M5 평가 결과 (eval/run_eval.py가 만든 results.json). 화면의 '품질' 섹션용."""
    import json

    from ..config import ROOT
    p = ROOT / "eval" / "results.json"
    if not p.exists():
        return {"available": False}
    return {"available": True, **json.loads(p.read_text(encoding="utf-8"))}
