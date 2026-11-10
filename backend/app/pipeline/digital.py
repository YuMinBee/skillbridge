"""공공기관 전 직무의 디지털·AI 역량 요구 분석 (잡알리오 실공고).

질문
1. 공공기관 공고 중 디지털 역량(사무 디지털 · IT·보안 자격 · 데이터 · AI)을 요구하는 비율은? 직무 분야(NCS)별로는?
2. 그 요구는 '실무 역량'으로 적혀 있나, '자격증'으로만 적혀 있나?
3. 대경권과 전국은 다른가?

공고의 자격요건·우대조건 문장만 보므로(첨부 공고문 제외) 하한값이다. 분석 단위는 공고 1건.
"""
from collections import Counter

from ..skills import get_dict
from . import supply
from .market import REGIONS, _filter

GROUPS = {
    "office": ("사무 디지털", {"office", "excel", "cert_computer", "cert_office"}),
    "it": ("IT·보안 자격", {"cert_info_processing", "cert_security", "cert_network"}),
    "data": ("데이터", {"cert_data", "stat_tool", "data_analysis", "sql", "python", "r_lang", "data_visualization", "pandas"}),
    "ai": ("AI", None),  # 아래 카테고리 전체
}
AI_CATEGORIES = {"머신러닝", "딥러닝", "생성형AI", "AI활용", "컴퓨터비전", "자연어처리"}
MIN_FIELD = 80  # 공고 수가 이보다 적은 NCS 분야는 표에서 뺀다 (비율이 흔들림)


def _groups_of(skill_ids, sd) -> set[str]:
    out = set()
    for s in skill_ids:
        cat = sd.skills.get(s, {}).get("category")
        if cat in AI_CATEGORIES:
            out.add("ai")
        for g, (_, members) in GROUPS.items():
            if members and s in members:
                out.add(g)
    return out


def _pct(a, b):
    return round(a / b * 100, 1) if b else 0.0


def _stats(rows, sd) -> dict:
    n = len(rows)
    tagged = [(r, _groups_of(r["skills"], sd)) for r in rows]
    dig = [(r, g) for r, g in tagged if g]
    cert_only = sum(1 for r, g in dig
                    if all(sd.skills[s]["category"] == "자격증" for s in r["skills"] if _groups_of([s], sd)))
    return {"n": n, "digital": _pct(len(dig), n),
            "groups": {g: _pct(sum(1 for _, gs in tagged if g in gs), n) for g in GROUPS},
            "cert_only": _pct(cert_only, len(dig)), "n_digital": len(dig)}


def digital_map(region: str = "dg") -> dict:
    sd = get_dict()
    sel, months = _filter(region, "public")
    if not sel:
        return {"available": False}
    overall = _stats(sel, sd)
    nation = _stats(_filter("all", "public")[0], sd) if region != "all" else overall

    fields = Counter(f for r in sel for f in r.get("ncs", []))
    by_field = []
    for f, c in fields.most_common():
        if c < MIN_FIELD:
            continue
        st = _stats([r for r in sel if f in r.get("ncs", [])], sd)
        by_field.append({"field": f, **st})
    by_field.sort(key=lambda x: -x["digital"])

    non_it = [r for r in sel if "정보통신" not in r.get("ncs", [])]
    top = Counter(s for r in sel for s in r["skills"] if _groups_of([s], sd)).most_common(10)
    examples = []
    for g in ("ai", "data"):
        hit = next((r for r in reversed(sel) if g in _groups_of(r["skills"], sd)), None)
        if hit:
            s = next(s for s in hit["skills"] if g in _groups_of([s], sd))
            examples.append({"group": GROUPS[g][0], "skill": sd.name(s), "text": hit["skills"][s]["evidence"][:160],
                             "company": hit["company"], "date": hit["date"], "url": hit.get("url", "")})
    # 그 역량을 배울 지역 대면 교육 (스킬별 정원 합 · 한 과정이 여러 스킬에 걸치면 중복)
    sup = supply.load() or {"skills": {}}
    group_supply = {}
    for g in GROUPS:
        ids = [s for s in sup["skills"] if g in _groups_of([s], sd)]
        group_supply[g] = {k: sum(sup["skills"][s].get(k, {}).get("seats", 0) for s in ids) for k in ("대경권", "수도권")}
        group_supply[g]["online_rounds_min"] = sum(sup["skills"][s].get("online_rounds_min", 0) for s in ids)
    group_supply["ai"]["ai_use_dg"] = sum(sup["skills"][s].get("대경권", {}).get("seats", 0) for s in sup["skills"]
                                          if sd.skills.get(s, {}).get("category") == "AI활용")
    # 수집기가 과정을 검색하지 않은 범주(도구 등)는 공급을 모른다 → None
    by_skill_supply = {s: (None if sd.skills[s]["category"] in supply.SKIP_CATEGORIES
                           else sup["skills"].get(s, {}).get("대경권", {}).get("seats", 0)) for s, _ in top}

    return {
        "available": True, "group_supply": group_supply, "region": REGIONS[region], "period": f"{months[0]} ~ {months[-1]}" if months else "",
        "labels": {g: v[0] for g, v in GROUPS.items()},
        "overall": overall, "nation": nation, "non_it": _stats(non_it, sd),
        "by_field": by_field, "min_field": MIN_FIELD,
        "top_skills": [{"skill_id": s, "name": sd.name(s), "category": sd.skills[s]["category"], "pct": _pct(c, len(sel)),
                        "dg_seats": by_skill_supply.get(s, 0)}
                       for s, c in top],
        "examples": examples,
        "source": f"잡알리오 실공고 {len(sel):,}건 · 자격요건·우대조건 문장 기준(첨부 공고문 제외 → 하한값)",
    }
