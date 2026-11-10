"""교육 공급 × 시장 수요: 지역에서 수요는 있는데 대면 교육이 없는 '공급 공백' 스킬을 찾는다.

공급은 collectors/build_supply.py가 고용24 훈련과정 전수 수집에서 만든 seed/market/supply_live.json.
수요는 market.rates(지역, 직무) — 공고 언급률.
"""
import json
from functools import lru_cache

from ..config import SEED
from ..skills import get_dict
from . import market

SUPPLY = SEED / "market" / "supply_live.json"
MIN_DEMAND = 5.0  # 언급률 5% 미만 스킬은 그리지 않는다
SKIP_CATEGORIES = {"협업", "도구", "연구", "도메인"}  # 수집기에서 검색하지 않은 범주 → 공급 0이 '공백'이란 뜻이 아님


@lru_cache(maxsize=1)
def load() -> dict | None:
    return json.loads(SUPPLY.read_text(encoding="utf-8")) if SUPPLY.exists() else None


def status(seats: int, online: int) -> str:
    if seats > 0:
        return "있음"
    return "원격만" if online > 0 else "공백"


def gap_map(region: str, job: str) -> dict:
    sup = load()
    if sup is None:
        return {"available": False}
    sd = get_dict()
    demand = market.rates(region, job)
    groups = ["대경권"] if region == "dg" else ["대경권", "수도권"]
    points = []
    for sid, d in sorted(demand.items(), key=lambda x: -x[1]):
        if d < MIN_DEMAND or sd.skills.get(sid, {}).get("category") in SKIP_CATEGORIES:
            continue
        s = sup["skills"].get(sid, {})
        seats = sum(s.get(g, {}).get("seats", 0) for g in groups)
        rounds = sum(s.get(g, {}).get("rounds", 0) for g in groups)
        online = s.get("online_rounds_min", 0)
        points.append({"skill_id": sid, "name": sd.name(sid), "demand_pct": round(d, 1), "seats": seats, "rounds": rounds,
                       "online_rounds": online, "capital_seats": s.get("수도권", {}).get("seats", 0),
                       "status": status(seats, online),
                       "example": next((s.get(g, {}).get("example") for g in groups if s.get(g, {}).get("example")), "")})
    t = sup["totals"]
    return {
        "available": True, "region": market.REGIONS[region], "job": market.JOBS[job],
        "supply_scope": " + ".join(groups) + " 대면 과정",
        "window": sup["window"], "points": points,
        "totals": t,
        "headline": {"dg_share": t["대경권"]["tech_share_pct"], "capital_share": t["수도권"]["tech_share_pct"],
                     "ratio": round(t["수도권"]["tech_share_pct"] / t["대경권"]["tech_share_pct"], 1)
                     if t["대경권"]["tech_share_pct"] else None},
        "gaps": [p["name"] for p in points if p["status"] == "공백"],
        "source": {"supply": f"고용24 훈련과정 API 전수 수집 ({sup['window'][0]}~{sup['window'][1]} 개강)",
                   "demand": "시장 탭과 같은 공고 집계"},
    }
