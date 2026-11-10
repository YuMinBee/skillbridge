"""학습경로: 필수 갭 우선, 공공 과정으로 기초 → 기업 트랙으로 마무리.

- 추천 과정은 카탈로그(seed 또는 훈련과정 API)에 있는 것만 낸다. 없으면 '자습 + 결과물' 단계로 표시.
- verify(검증 필요)는 강의 대신 '결과물로 증명하기' 과제를 낸다.
- part(부분)는 과정 시간의 절반만 잡는다 (기초를 일부 갖췄다고 보고 심화 위주로).
- LONG_HOURS를 넘는 장기 과정(KDT 등)은 경로 시간에 넣지 않는다. 기업 트랙이 있으면 트랙으로,
  없으면 자습 단계에 '참고 과정'으로만 붙인다.
"""
import math

from ..data import courses
from ..skills import get_dict
from .score import WEIGHT_LABEL, gaps

PROOF_HOURS = 6
SELF_STUDY_HOURS = 10
LONG_HOURS = 160


def _rank(region: str, sid: str):
    # 과정명에서 그 스킬이 가장 먼저 나오는(=주제인) 과정을 우선한다. 예: 'LLM' 갭에 '자바 입문+챗GPT'보다 'LLM 파인튜닝'
    return lambda c: (0 if c["skills"][0] == sid else 1, 0 if c["region"] in (region, "전국") else 1,
                      0 if c["level"] == "기초" else 1, c["hours"], c["id"])


def _pick_course(sid: str, region: str):
    """(경로에 넣을 과정, 장기 과정만 있을 때 참고용 과정)"""
    cands = [c for c in courses() if sid in c["skills"]]
    short = [c for c in cands if c["hours"] <= LONG_HOURS]
    if short:
        return min(short, key=_rank(region, sid)), None
    if cands:
        return None, min(cands, key=_rank(region, sid))
    return None, None


def _course_meta(c: dict) -> str:
    bits = [c["provider"], f"{c['hours']}시간", c["level"], c["region"]]
    if c.get("start"):
        bits.append(f"{c['start']} 개강")
    return " · ".join(b for b in bits if b)


TIER_LABEL = {"apply": "지원 기준", "work": "실무 기준"}


def tiered_gaps(requirements: dict[str, int], status_map: dict[str, dict],
                apply_reqs: dict[str, int] | None = None) -> list[tuple[str, int, str, str]]:
    """(스킬, 가중치, 상태, 단계) — 공고(지원 기준) 갭을 먼저, 기업이 등록한 실무 기준 갭을 나중에.
    공고와 실무 기준에 모두 있으면 지원 단계로 보고 둘 중 큰 가중치를 쓴다."""
    if not apply_reqs:
        return [(s, w, st, "work") for s, w, st in gaps(requirements, status_map)]
    out = [(s, max(w, requirements.get(s, 0)), st, "apply") for s, w, st in gaps(apply_reqs, status_map)]
    out += [(s, w, st, "work") for s, w, st in gaps(requirements, status_map) if s not in apply_reqs]
    return out


def build_path(requirements: dict[str, int], status_map: dict[str, dict], company: dict,
               weekly_hours: int, apply_reqs: dict[str, int] | None = None) -> dict:
    """requirements = 기업 실무 기준, apply_reqs = 공고(지원) 기준. apply_reqs가 있으면 두 기준의 갭을 모두 다룬다."""
    sd = get_dict()
    steps: list[dict] = []
    used_course: dict[str, dict] = {}
    used_track: set[str] = set()

    for sid, w, st, tier in tiered_gaps(requirements, status_map, apply_reqs):
        name = sd.name(sid)
        base = {"skill_id": sid, "skill": name, "weight": w, "weight_label": WEIGHT_LABEL[w], "status": st,
                "tier": tier, "tier_label": TIER_LABEL[tier]}
        if st == "verify":
            steps.append({**base, "kind": "proof", "title": f"{name} 결과물로 증명하기", "hours": PROOF_HOURS,
                          "meta": "이력서에 키워드만 있음 → 작은 실습 결과물(GitHub)과 README로 근거를 남기면 '보유'로 바뀝니다"})
        else:
            tracks = [t for t in company.get("tracks", []) if sid in t["skills"] and t["id"] not in used_track]
            c, long_c = _pick_course(sid, company.get("region", "전국"))
            skip_public = st == "part" and tracks  # 부분 보유 + 기업 트랙이 있으면 트랙으로 바로
            if c and not skip_public:
                if c["id"] in used_course:
                    used_course[c["id"]]["covers"].append(name)
                else:
                    h = c["hours"] if st == "miss" else math.ceil(c["hours"] / 2)
                    step = {**base, "kind": "public", "title": c["title"], "hours": h, "course_id": c["id"],
                            "covers": [name], "link": c.get("link", ""),
                            "meta": _course_meta(c) + (" · 부분 보유라 절반 반영" if st == "part" else "")}
                    used_course[c["id"]] = step
                    steps.append(step)
            elif not c and not tracks:
                step = {**base, "kind": "self", "title": f"{name} 공식 문서 자습 + 미니 결과물", "hours": SELF_STUDY_HOURS,
                        "meta": "카탈로그에 맞는 단기 공공 과정이 없어 자습으로 대체합니다"}
                if long_c:
                    step["meta"] = f"단기 과정이 없어 자습으로 대체 · 참고: {long_c['title']} ({_course_meta(long_c)})"
                    step["ref_course_id"], step["link"] = long_c["id"], long_c.get("link", "")
                steps.append(step)
            for t in tracks:
                used_track.add(t["id"])
                steps.append({**base, "kind": "corp", "title": t["title"], "hours": t["hours"], "track_id": t["id"],
                              "meta": " · ".join(x for x in [f"{t['hours']}시간", t.get("benefit", "")] if x)})

    total = sum(s["hours"] for s in steps)
    by_kind = {k: sum(s["hours"] for s in steps if s["kind"] == k) for k in ("public", "corp", "proof", "self")}
    wh = max(1, int(weekly_hours or 1))
    return {"steps": steps, "total_hours": total, "hours_by_kind": by_kind, "weekly_hours": wh,
            "weeks": math.ceil(total / wh) if total else 0}


# ── 시간당 효과 순서 최적화 ───────────────────────────────
# JCRec(arXiv 2404.10876)처럼 '과정을 마치면 시장 공고에 얼마나 더 맞게 되는가'를 보상에 넣는다.
# 보상 = 기업 준비도 상승(점) + 시장 공고 평균 적합도 상승(점). 둘 다 0~100 척도. 이를 시간으로 나눈 값이 큰 단계부터 고른다(탐욕법).
# 논문처럼 '지원 가능 공고 수(70점 이상)'만 쓰면 공고당 요구 스킬이 많아 거의 움직이지 않아서, 평균 적합도를 주 지표로 쓰고 지원 가능 비율은 함께 보고한다.
# 같은 스킬 안에서는 공공 과정 → 기업 트랙 순서를 지킨다. 탐욕법은 논문에서도 짧은 경로(1~3단계)에서 가장 좋았다.
QUALIFY = 70  # 공고 기준 준비도가 이 점수 이상이면 '지원 가능'

_AFTER = {  # 단계를 마친 뒤 그 스킬의 상태
    "public": {"miss": "part", "part": "own", "verify": "own"},
    "corp": {"miss": "own", "part": "own", "verify": "own"},
    "proof": {"verify": "own", "part": "own", "miss": "part"},
    "self": {"miss": "part", "part": "own", "verify": "own"},
}


def _market_fit(postings: list[dict[str, int]], status: dict) -> tuple[float, float]:
    """(공고 평균 적합도, 지원 가능 공고 비율 %)"""
    from .score import readiness
    ps = [p for p in postings if p]
    if not ps:
        return 0.0, 0.0
    sc = [readiness(p, status) for p in ps]
    return sum(sc) / len(sc), sum(x >= QUALIFY for x in sc) / len(sc) * 100


def optimize_order(path: dict, status_map: dict, requirements: dict[str, int], postings: list[dict[str, int]],
                   apply_reqs: dict[str, int] | None = None) -> dict:
    """단계(지원 → 실무)는 지키고, 각 단계 안에서 시간당 효과가 큰 순으로 고른다.
    보상: 지원 단계 = 지원 준비도 상승 + 시장 적합도 상승, 실무 단계 = 실무 준비도 상승 + 시장 적합도 상승."""
    from .score import readiness

    def apply(st, step):
        cur = st.get(step["skill_id"], {}).get("status", "miss")
        nxt = _AFTER[step["kind"]].get(cur, cur)
        return {**st, step["skill_id"]: {"status": nxt}}

    areqs = apply_reqs or {}
    status = {k: {"status": v["status"]} for k, v in status_map.items()}
    r0, a0 = readiness(requirements, status), readiness(areqs, status) if areqs else None
    f0, q0 = _market_fit(postings, status)
    r_cur, a_cur, f_cur, q_cur, ordered = r0, a0, f0, q0, []
    for tier in ("apply", "work"):
        remaining = [s for s in path["steps"] if s.get("tier", "work") == tier]
        target = areqs if tier == "apply" else requirements
        while remaining:
            # 같은 스킬의 앞 단계가 남아 있으면 뒤 단계는 아직 고를 수 없다
            firsts = [s for i, s in enumerate(remaining) if all(p["skill_id"] != s["skill_id"] for p in remaining[:i])]
            best = None
            for s in firsts:
                st2 = apply(status, s)
                t_gain = readiness(target, st2) - readiness(target, status)
                f2, q2 = _market_fit(postings, st2)
                gain = t_gain + (f2 - f_cur)
                key = (gain / max(1, s["hours"]), gain, -s["hours"])
                if best is None or key > best[0]:
                    best = (key, s, st2, f2, q2)
            _, s, status, f2, q2 = best
            r2 = readiness(requirements, status)
            a2 = readiness(areqs, status) if areqs else None
            s["gain"] = {"readiness": r2 - r_cur, "market_fit": round(f2 - f_cur, 1), "per_hour": round(best[0][0], 2),
                         "readiness_after": r2, "market_fit_after": round(f2, 1), "qualified_after": round(q2, 1),
                         "apply": (a2 - a_cur) if areqs else None, "apply_after": a2}
            r_cur, a_cur, f_cur, q_cur = r2, a2, f2, q2
            ordered.append(s)
            remaining.remove(s)
    return {**path, "steps": ordered, "optimized": True,
            "apply_before": a0, "apply_after": a_cur, "work_before": r0, "work_after": r_cur,
            "market": {"postings": len(postings), "fit_before": round(f0, 1), "fit_after": round(f_cur, 1),
                       "qualified_before": round(q0, 1), "qualified_after": round(q_cur, 1), "threshold": QUALIFY}}
