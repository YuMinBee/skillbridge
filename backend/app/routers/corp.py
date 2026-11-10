"""기업 콘솔 API.

데모에는 로그인이 없으므로 경로의 tenant_id로 기업을 고른다. 배포(M4/M6) 시에는
tenant_id를 인증 토큰에서 꺼내고 경로 값과 다르면 거부한다 (guards/tenant.py).
"""
from collections import Counter

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..adapters import storage
from ..data import courses, courses_source, fake_sessions
from ..pipeline import market
from ..pipeline.diagnose import effective_requirements
from ..pipeline.recommend import LONG_HOURS
from ..pipeline.simulate import simulate
from ..skills import get_dict

router = APIRouter(prefix="/api/companies", tags=["corp"])

RARE_REQUIRED, SOMEWHAT_RARE = 15, 30


def _get(tid: str) -> dict:
    c = storage.get_company(tid)
    if c is None:
        raise HTTPException(404, f"기업 {tid}를 찾을 수 없습니다")
    return c


def _view(c: dict) -> dict:
    sd = get_dict()
    rates = market.rate_for_company(c)
    reqs = [{"skill_id": s, "name": sd.name(s), "weight": w, "market_pct": round(rates.get(s, 0), 1)}
            for s, w in sorted(c["requirements"].items(), key=lambda x: (-x[1], x[0]))]
    tracks = [{**t, "skill_names": [sd.name(s) for s in t["skills"]]} for t in c.get("tracks", [])]
    return {**c, "requirements_view": reqs, "tracks": tracks,
            "market_scope": f"{'대경권' if c.get('region') == '대경권' else '전국'} · {market.JOBS.get(c.get('job'), '')}"}


@router.get("")
def list_companies():
    return [{"id": c["tenant_id"], "name": c["name"], "desc": c.get("desc", ""), "region": c.get("region"),
             "job": c.get("job")} for c in storage.list_companies()]


@router.get("/{tid}")
def get_company(tid: str):
    return _view(_get(tid))


class ReqIn(BaseModel):
    requirements: dict[str, int]


@router.put("/{tid}/requirements")
def put_requirements(tid: str, body: ReqIn):
    _get(tid)
    sd = get_dict()
    bad = [s for s in body.requirements if not sd.exists(s)]
    if bad:
        raise HTTPException(400, f"사전에 없는 스킬: {', '.join(bad)}")
    reqs = {s: w for s, w in body.requirements.items() if w in (1, 2)}  # 0 = 제외
    if not reqs:
        raise HTTPException(400, "요구역량이 최소 1개는 있어야 합니다")
    return _view(storage.update_company(tid, requirements=reqs))


class TrackIn(BaseModel):
    id: str | None = None
    skills: list[str] = Field(min_length=1)
    title: str = Field(min_length=1, max_length=80)
    hours: int = Field(ge=1, le=200)
    benefit: str = Field("", max_length=80)


class TracksIn(BaseModel):
    tracks: list[TrackIn] = Field(max_length=20)


@router.put("/{tid}/tracks")
def put_tracks(tid: str, body: TracksIn):
    _get(tid)
    sd = get_dict()
    out, n = [], 0
    for t in body.tracks:
        bad = [s for s in t.skills if not sd.exists(s)]
        if bad:
            raise HTTPException(400, f"사전에 없는 스킬: {', '.join(bad)}")
        n += 1
        out.append({"id": t.id or f"{tid}-T{n}", "skills": t.skills, "title": t.title.strip(), "hours": t.hours,
                    "benefit": t.benefit.strip()})
    ids = [t["id"] for t in out]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "트랙 ID가 중복됩니다")
    return _view(storage.update_company(tid, tracks=out))


class DocIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


@router.post("/{tid}/docs")
def suggest_from_doc(tid: str, body: DocIn):
    """기업 자료(JD·블로그·스택 설명) → 요구역량 초안 제안.
    M4에서 이 문서를 S3 corp-docs/{tenantId}/에 저장하고 Knowledge Base에 적재한다."""
    c = _get(tid)
    sd = get_dict()
    rates = market.rate_for_company(c)
    hits = sd.find(body.text)
    cnt = Counter(h["skill_id"] for h in hits)
    cur = effective_requirements(c)
    sugg = []
    for sid, k in cnt.most_common():
        sugg.append({"skill_id": sid, "name": sd.name(sid), "mentions": k,
                     "suggested_weight": 2 if k >= 2 else 1, "market_pct": round(rates.get(sid, 0), 1),
                     "already": cur.get(sid)})
    # 우리 회사 문서(지식베이스)에서 그 스킬이 나오는 문단을 근거로 붙인다. tenant 필터는 kb 안에서 강제
    kb_note = _attach_kb_evidence(tid, sugg[:6])
    return {"suggestions": sugg, "kb": kb_note}


def _attach_kb_evidence(tid: str, items: list[dict]) -> str:
    from ..adapters import kb
    try:
        for s in items:
            hits = kb.retrieve(tid, f"{s['name']} 사용 업무", k=1)
            s["kb_evidence"] = hits[0] if hits else None
    except Exception as e:  # noqa: BLE001 — 근거 검색이 실패해도 제안은 낸다
        return f"지식베이스 검색 실패: {str(e)[:120]}"
    return ("Bedrock Knowledge Base (S3 Vectors · Titan V2) · tenantId 필터 서버 강제" if kb.mode() == "kb"
            else "로컬 문서 검색 (KB_ID 미설정 또는 MOCK) · 같은 기업 문서만")


@router.get("/{tid}/evidence")
def kb_evidence(tid: str, q: str):
    """기업 지식베이스 근거 검색. tid는 저장소에 있는 기업이어야 하고, 결과는 그 기업 문서뿐이다."""
    from ..adapters import kb
    _get(tid)
    if not q.strip() or len(q) > 300:
        raise HTTPException(400, "q는 1~300자")
    return {"mode": kb.mode(), "results": kb.retrieve(tid, q, k=4)}


@router.get("/{tid}/insights")
def insights(tid: str):
    c = _get(tid)
    sd = get_dict()
    reqs = effective_requirements(c)
    sessions = [s["gaps"] for s in fake_sessions() if s["company"] == tid] + storage.sessions_for(tid)
    n = len(sessions)
    cnt = Counter(g for gs in sessions for g in gs)
    blocked = sorted(({"skill_id": s, "name": sd.name(s), "pct": round(cnt.get(s, 0) / n * 100) if n else 0}
                      for s in reqs), key=lambda x: -x["pct"])
    rates = market.rate_for_company(c)
    cat = courses()
    vs = []
    for s, w in sorted(reqs.items(), key=lambda x: (-x[1], x[0])):
        r = rates.get(s, 0)
        if w == 2 and r < RARE_REQUIRED:
            judge, level = "희소 · 필수로 두면 지원자 풀이 좁아짐 → 교육 트랙으로 보완 권장", "bad"
        elif w == 2 and r < SOMEWHAT_RARE:
            judge, level = "다소 희소 · 트랙 제공 고려", "warn"
        else:
            judge, level = "일반적", "ok"
        short = [x for x in cat if s in x["skills"] and x["hours"] <= LONG_HOURS]
        track = any(s in t["skills"] for t in c.get("tracks", []))
        vs.append({"skill_id": s, "name": sd.name(s), "weight": w, "market_pct": round(r, 1), "judge": judge, "level": level,
                   "public_courses": len(short), "has_track": track,
                   "course_gap": not short})
    return {"sessions": n, "fake_included": True, "blocked": blocked[:8], "vs_market": vs,
            "courses_source": courses_source(),
            "market_scope": f"{'대경권' if c.get('region') == '대경권' else '전국'} · {market.JOBS.get(c.get('job'), '')}"}


class SimIn(BaseModel):
    requirements: dict[str, int] | None = None  # 없으면 현재 기준
    assume_tracks: bool = False


@router.post("/{tid}/simulate")
def simulate_criteria(tid: str, body: SimIn):
    """요구역량을 바꿨을 때 지원자 풀(익명 상태 코드)의 준비도 분포. 저장하지 않는다."""
    c = _get(tid)
    if body.requirements is not None:
        sd = get_dict()
        bad = [k for k in body.requirements if not sd.exists(k)]
        if bad:
            raise HTTPException(400, f"알 수 없는 스킬: {', '.join(bad)}")
        if not any(v in (1, 2) for v in body.requirements.values()):
            raise HTTPException(400, "필수 또는 우대 역량이 하나 이상 필요합니다")
    return simulate(c, body.requirements, body.assume_tracks)
