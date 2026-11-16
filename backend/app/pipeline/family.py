"""직군 지도: 같은 직군 회사들의 '공고 수요'와 '실무 중요도'를 스킬마다 계산한다 (규칙, LLM 없음).

- 공고 수요 x  = 직군 회사 공고에서 그 스킬의 평균 가중치 / 2   (필수 2 · 우대 1 · 없음 0 → 0~1)
- 실무 중요도 y = 직군 회사 실무 기준에서 그 스킬의 평균 가중치 / 2
'A 또는 B' 요건(any_of)은 지원자에게 맞춰 하나로 줄인 뒤 센다.
추천 순서(화면에서 λ로 조절): 부족도 × (x + λ·y) / (1 + λ),  부족도 = 없음 1 · 부분/검증 필요 0.5 · 보유 0
"""
from ..data import hidden_ids, seed_companies
from ..skills import get_dict
from .extract import STATUS_LABEL as STATUS_LABEL_SHORT, posting_requirements
from .score import resolve_any_of, status_of

NEED = {"miss": 1.0, "part": 0.5, "verify": 0.5, "own": 0.0}
SOFT = {"communication", "english", "technical_writing", "agile"}  # 과정으로 메우는 기술이 아니라 지도에서 뺀다


def family_of(c: dict) -> str:
    return c.get("job_family") or seed_companies().get(c["tenant_id"], {}).get("job_family", "기타")


def family_map(family: str, companies: list[dict], status_map: dict, effective) -> dict:
    sd = get_dict()
    hidden = hidden_ids()
    comps = [c for c in companies if family_of(c) == family and c["tenant_id"] not in hidden]
    n = len(comps)
    if n == 0:
        return {"family": family, "n": 0, "skills": []}
    seeds = seed_companies()
    px: dict[str, float] = {}
    wy: dict[str, float] = {}
    nw: dict[str, int] = {}
    for c in comps:
        groups = c.get("any_of") or seeds.get(c["tenant_id"], {}).get("any_of") or []
        apply = c.get("apply_requirements") or posting_requirements(c.get("posting_text", ""))
        apply = resolve_any_of(apply, groups, status_map)
        work = effective(c, status_map)
        for s, w in apply.items():
            px[s] = px.get(s, 0) + w
        for s, w in work.items():
            wy[s] = wy.get(s, 0) + w
            nw[s] = nw.get(s, 0) + 1
    skills = []
    for s in (set(px) | set(wy)) - SOFT:
        st = status_of(status_map, s)
        skills.append({"skill_id": s, "name": sd.name(s), "x": round(px.get(s, 0) / (2 * n), 3),
                       "y": round(wy.get(s, 0) / (2 * n), 3), "status": st, "status_label": STATUS_LABEL_SHORT[st],
                       "need": NEED[st],
                       "n_work": nw.get(s, 0),
                       })
    skills.sort(key=lambda k: -(k["x"] + k["y"]))
    return {"family": family, "n": n, "companies": [c["name"] for c in comps], "skills": skills,
            "formula": "우선순위 = 부족도 × (공고 수요 + λ·실무 중요도) ÷ (1 + λ) · 부족도: 없음 1 / 부분·검증 필요 0.5 / 보유 0"}


# ── 목록에 없는 회사 (예: 삼성 개발직) ─────────────────────────────
AI_FAMILIES = {"AI·ML 엔지니어", "MLOps·AI 플랫폼", "데이터 엔지니어·분석"}
WORK_MIN, WORK_MUST = 0.2, 0.4  # 직군 실무 중요도 0.2 이상이면 기준에 넣고, 0.4 이상이면 필수


def _family_companies(family: str, companies: list[dict]) -> list[dict]:
    hidden = hidden_ids()
    return [c for c in companies if family_of(c) == family and c["tenant_id"] not in hidden]


def custom_company(name: str, family: str, posting_text: str, companies: list[dict], effective) -> dict:
    """실무 기준이 등록되지 않은 회사: 지원 기준은 붙여 넣은 공고, 실무 기준은 '같은 직군 회사들의 실무 기준'으로 추정."""
    comps = _family_companies(family, companies)
    n = max(1, len(comps))
    tot: dict[str, int] = {}
    who: dict[str, list[dict]] = {}
    for c in comps:
        for s, w in effective(c, {}).items():
            tot[s] = tot.get(s, 0) + w
            src = (c.get("sources") or {}).get(s, {})
            who.setdefault(s, []).append({"company": c["name"], "from": src.get("from", ""), "quote": src.get("quote", ""),
                                          "url": src.get("url", "")})
    reqs, evid = {}, []
    sd = get_dict()
    for s, t in sorted(tot.items(), key=lambda x: -x[1]):
        y = t / (2 * n)
        if y >= WORK_MIN:
            reqs[s] = 2 if y >= WORK_MUST else 1
        evid.append({"skill_id": s, "name": sd.name(s), "y": round(y, 3), "n_companies": len(who[s]), "examples": who[s][:3]})
    return {"tenant_id": "custom", "custom": True, "name": name, "desc": f"{family} · 직접 입력",
            "job_family": family, "job_title": family, "region": "미상",
            "job": "ai" if family in AI_FAMILIES else "cloud", "posting_text": posting_text,
            "apply_source": "붙여 넣은 공고", "work_source": f"같은 직군 {len(comps)}곳 실무 기준(추정)",
            "requirements": reqs, "sources": {}, "excluded": [], "tracks": [],
            "domain": {"label": family, "keywords": []},
            "_family_evidence": evid[:12], "_family_n": len(comps)}


_PREDICT_SYS = """너는 채용 분석가다. 한 회사의 채용 공고와, 같은 직군의 다른 회사들이 입사 후 실무에서 쓰는 기술 통계를 받는다.
이 회사가 입사 후 실무에서 쓸 가능성이 높은데 공고에는 드러나지 않은 기술을 최대 6개 고른다.
규칙:
- skill_id는 반드시 <후보> 목록에 있는 것만 쓴다.
- reason은 한 문장. 공고 문장이나 직군 통계(몇 곳 중 몇 곳)를 근거로 든다. 회사 내부 사정을 아는 척하지 않는다.
- 공고에 이미 요구된 기술은 고르지 않는다."""

_PREDICT_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {"skill_id": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["skill_id", "reason"]}}}, "required": ["items"]}


def predict_work(company: dict, preqs: dict, status_map: dict, log=None) -> dict:
    """'이 회사는 실무에서 이런 기술을 쓸 것 같아요' — 참고용 예측. 점수에는 넣지 않는다."""
    from ..adapters import bedrock
    sd = get_dict()
    n = company["_family_n"]
    cands = [e for e in company["_family_evidence"] if e["skill_id"] not in preqs]

    def item(sid, reason):
        e = next((x for x in company["_family_evidence"] if x["skill_id"] == sid), None)
        return {"skill_id": sid, "name": sd.name(sid), "reason": reason, "status": status_of(status_map, sid),
                "status_label": STATUS_LABEL_SHORT[status_of(status_map, sid)],
                "n_companies": e["n_companies"] if e else 0}

    rule = [item(e["skill_id"], f"{company['job_family']} {n}곳 중 {e['n_companies']}곳이 실무에서 사용") for e in cands[:6]]
    if bedrock.mode() == "mock" or not cands:
        return {"mode": "rules", "items": rule}
    lines = "\n".join(f"- {e['skill_id']} ({e['name']}): {n}곳 중 {e['n_companies']}곳 실무 사용" for e in cands[:20])
    user = f"<회사>{company['name']} · {company['job_family']}</회사>\n<공고>\n{company['posting_text'][:4000]}\n</공고>\n<후보>\n{lines}\n</후보>"
    try:
        out = bedrock.converse_tool(_PREDICT_SYS, user, "submit_prediction", _PREDICT_SCHEMA, log=log, kind="predict",
                                    max_tokens=1200)
        ok = {e["skill_id"] for e in cands[:20]}
        items = [item(x["skill_id"], x["reason"].strip()) for x in out.get("items", []) if x.get("skill_id") in ok][:6]
        return {"mode": "bedrock", "items": items or rule}
    except bedrock.BedrockError:
        return {"mode": "rules", "items": rule}
