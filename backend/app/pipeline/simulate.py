"""기업 기준 시뮬레이터: 요구역량을 바꾸면 우리 지원자 풀의 준비도 분포가 어떻게 바뀌는가.

지원자 풀 = 이 기업에 진단한 익명 기록의 스킬 상태 코드 (시연용 가상 기록 + 실제 진단).
준비도는 진단과 같은 규칙(score.readiness)으로 다시 계산한다 → 기업 화면과 취준생 화면이 같은 숫자를 쓴다.

질문 세 가지에 답한다.
1. 지금 기준에서 '지원 가능선'(준비도 THRESHOLD점 이상)을 넘는 지원자는 몇 %인가
2. 제안한 기준(필수→우대, 제외 등)이면 몇 %가 되는가
3. 어떤 한 가지를 바꾸면 효과가 가장 큰가 (레버 순위), 우리 교육 트랙을 이수하면 어떻게 되는가
"""
from statistics import median

from ..adapters import storage
from ..data import fake_sessions
from ..skills import get_dict
from .diagnose import effective_requirements
from .score import WEIGHT_LABEL, readiness

THRESHOLD = 70
BINS = list(range(0, 101, 10))  # 0-9, 10-19, …, 90-100


def pool(tid: str) -> list[dict[str, str]]:
    fake = [s.get("profile", {}) for s in fake_sessions() if s["company"] == tid and "profile" in s]
    return fake + storage.profiles_for(tid)


def _as_status_map(profile: dict[str, str]) -> dict:
    return {k: {"status": v} for k, v in profile.items()}


def _dist(reqs: dict[str, int], profiles: list[dict]) -> dict:
    scores = [readiness(reqs, _as_status_map(p)) for p in profiles]
    if not scores:
        return {"share": 0, "median": 0, "hist": [0] * 10, "n": 0}
    hist = [0] * 10
    for s in scores:
        hist[min(9, s // 10)] += 1
    return {"share": round(sum(s >= THRESHOLD for s in scores) / len(scores) * 100, 1),
            "median": median(scores), "hist": hist, "n": len(scores)}


def _with_tracks(profile: dict[str, str], track_skills: set[str]) -> dict[str, str]:
    """기업 트랙을 이수했다고 가정: 없음 → 부분, 부분·검증 필요 → 보유 (트랙 결과물이 근거가 된다)."""
    out = dict(profile)
    for s in track_skills:
        out[s] = "part" if s not in profile else "own"
    return out


def simulate(company: dict, proposed: dict[str, int] | None = None, assume_tracks: bool = False) -> dict:
    sd = get_dict()
    tid = company["tenant_id"]
    profiles = pool(tid)
    cur = effective_requirements(company)
    prop = {k: v for k, v in (proposed or cur).items() if v in (1, 2)}
    track_skills = {s for t in company.get("tracks", []) for s in t["skills"]}
    scen_profiles = [_with_tracks(p, track_skills) for p in profiles] if assume_tracks else profiles

    base, scen = _dist(cur, profiles), _dist(prop, scen_profiles)

    # 레버: 지금 기준에서 한 가지씩만 바꿨을 때의 효과 (필수→우대, 우대→제외)
    levers = []
    for s, w in cur.items():
        alt = dict(cur)
        if w == 2:
            alt[s], change = 1, "필수 → 우대"
        else:
            alt.pop(s)
            change = "우대 → 제외"
        d = _dist(alt, profiles)
        levers.append({"skill_id": s, "name": sd.name(s), "change": change, "share": d["share"],
                       "delta_pp": round(d["share"] - base["share"], 1), "has_track": s in track_skills})
    levers.sort(key=lambda x: (-x["delta_pp"], x["name"]))
    tr = _dist(cur, [_with_tracks(p, track_skills) for p in profiles]) if track_skills else None

    return {
        "n": len(profiles), "threshold": THRESHOLD, "fake_included": True,
        "current": base, "scenario": scen, "delta_pp": round(scen["share"] - base["share"], 1),
        "proposed": [{"skill_id": k, "name": sd.name(k), "weight": v, "weight_label": WEIGHT_LABEL[v]} for k, v in prop.items()],
        "assume_tracks": assume_tracks,
        "levers": levers[:6],
        "tracks_effect": None if tr is None else {"share": tr["share"], "delta_pp": round(tr["share"] - base["share"], 1),
                                                  "skills": [sd.name(s) for s in sorted(track_skills)]},
    }
