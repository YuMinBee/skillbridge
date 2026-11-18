"""검증 에이전트. 결과를 내보내기 전에 근거를 코드로 다시 확인한다 (LLM 판단 아님).

1. 강점: 채워진 STAR 칸의 인용이 이력서(가린 본문)에 실제로 있는가 → 없으면 그 칸을 비우고 점수를 다시 계산
2. 인용 목록: 이력서 인용은 원문에, 과정 인용은 고용24 카탈로그에 있는가 → 없으면 제거
3. 추천: 과정 이름이 카탈로그와 글자까지 같은가, 인용 번호가 살아 있는가 → 과정은 지우고, 근거가 하나도 없으면 '추천하지 않음'
"""
from ..data import courses
from . import star


def verify(result: dict, citations: list[dict], resume: str) -> tuple[dict, list[dict], dict]:
    catalog = {c["id"]: c for c in courses()}
    removed: list[str] = []

    # 1. 강점
    for e in result.get("strengths", []):
        changed = False
        for k, slot in e["slots"].items():
            if slot.get("present") and star.locate(slot.get("quote"), resume) is None:
                slot.update(quote=None, present=False)
                removed.append(f"strength:{e['exp_id']}:{k}")
                changed = True
        if changed:
            sc = star.score({k: s["quote"] for k, s in e["slots"].items()}, resume)
            e.update(score=sc["score"], level=sc["level"], missing_hint=sc["missing_hint"], my_role_clear=sc["my_role_clear"])
            e["slots"]["R"]["quantified"] = sc["quantified"]

    # 2. 인용
    alive = []
    for c in citations:
        ok = True
        if c["kind"] == "resume":
            ok = star.locate(c.get("quote"), resume) is not None
        elif c["kind"] == "course":
            ok = c.get("doc_id") in catalog
        if ok:
            alive.append(c)
        else:
            removed.append(f"citation:{c['n']}")
    live_n = {c["n"] for c in alive}

    # 3. 추천
    for r in result.get("recommendations", []):
        co = r.get("course")
        if co and (co.get("id") not in catalog or catalog[co["id"]]["title"] != co.get("name")):
            removed.append(f"course:{co.get('name')}")
            r["course"] = None
        r["cites"] = [n for n in r.get("cites", []) if n in live_n]
        if not r.get("abstained") and not r["cites"]:
            r.update(abstained=True, abstain_reason="근거를 확인하지 못해 추천하지 않음", task=None, course=None)
    for g in result.get("gaps", []):
        g["cites"] = [n for n in g.get("cites", []) if n in live_n]

    report = {"removed": removed, "passed": not removed,
              "checks": ["STAR 인용 ⊂ 이력서", "과정 ⊂ 고용24 카탈로그", "추천마다 살아 있는 인용 1개 이상"]}
    return result, alive, report
