"""슈퍼바이저. 단계를 계획·실행하고, 한 단계가 실패해도 나머지 결과를 낸다. CONTRACTS.md 5절의 result를 만든다.

단계: guard(개인정보) → star(① 강점) → skills(스킬 추출) → retriever(② 역량 기준) → recommend(③ 과제) → verifier → cost
- ②③은 T2 모듈(agents/retriever.py, agents/recommend_task.py)이 있으면 그것을 쓰고, 없으면 아래 임시 구현을 쓴다.
- 요청 예산(config.JOB_BUDGET_USD)을 넘으면 남은 LLM 단계는 규칙 엔진으로 돈다.
- 이력서 원문은 저장하지 않는다. 결과에는 인용 문장만 남는다(규칙 7).
"""
import importlib
import time
from contextlib import contextmanager

from ..adapters import bedrock
from ..config import GUARDRAIL_ID
from ..data import seed_companies, hidden_ids
from ..guards import pii
from ..pipeline import implies
from ..pipeline.extract import extract_resume, extract_resume_llm, posting_requirements, STATUS_LABEL
from ..pipeline.family import SOFT, family_of
from ..pipeline.recommend import _pick_course
from ..pipeline.score import gaps as score_gaps, readiness, resolve_any_of
from ..skills import get_dict, sentences
from . import cost, star, verifier

AGENTS = ["guard", "star", "skills", "retriever", "recommend", "verifier", "cost"]
FAMILIES = {"backend": ("백엔드",), "ai_ml": ("AI·ML", "MLOps"), "data": ("데이터",)}
FAMILY_LABEL = {"backend": "백엔드", "ai_ml": "AI·ML", "data": "데이터"}
APPLY_MIN, APPLY_MUST = 0.25, 0.5   # 같은 직군 공고에서 평균 가중치/2가 이 값 이상이면 기준, 이상이면 필수
MAX_RECO = 5


def _optional(name: str):
    try:
        return importlib.import_module(f"{__package__}.{name}")
    except ImportError:
        return None


class Cites:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, kind: str, title: str, quote: str | None, url: str | None = None, doc_id: str | None = None) -> int:
        for c in self.items:
            if c["kind"] == kind and c["doc_id"] == doc_id and c["quote"] == quote:
                return c["n"]
        n = len(self.items) + 1
        self.items.append({"n": n, "kind": kind, "doc_id": doc_id or kind, "title": title, "url": url, "quote": quote})
        return n


# ── ② 임시: 같은 직군 공고 기준 (T2의 NCS 검색이 들어오면 practice 기준이 추가된다) ──
def family_apply_requirements(job_family: str, status_map: dict) -> tuple[dict, dict]:
    keys = FAMILIES[job_family]
    hidden = hidden_ids()
    comps = [c for c in seed_companies().values()
             if c["tenant_id"] not in hidden and any(k in family_of(c) for k in keys) and c.get("posting_text")]
    tot: dict[str, float] = {}
    hit: dict[str, int] = {}
    for c in comps:
        req = c.get("apply_requirements") or posting_requirements(c["posting_text"])
        req = resolve_any_of(req, c.get("any_of") or [], status_map)
        for s, w in req.items():
            tot[s] = tot.get(s, 0) + w
            hit[s] = hit.get(s, 0) + 1
    n = max(1, len(comps))
    reqs = {}
    for s, t in tot.items():
        y = t / (2 * n)
        if y >= APPLY_MIN:
            reqs[s] = 2 if y >= APPLY_MUST else 1
    return reqs, {"n": len(comps), "hit": hit}


def _quote_in(text: str, name: str, aliases: list[str]) -> str | None:
    keys = [k.lower() for k in [name, *aliases] if k]
    for s in sentences(text):
        if any(k in s.lower() for k in keys):
            return s
    return None


def run(payload: dict, on_progress=None, log: "bedrock.CallLog | None" = None) -> dict:
    """payload = {resume(정규식 마스킹 끝난 본문), job_family, posting?} → {progress, result, citations, cost, trace, verify}"""
    log = log or bedrock.CallLog()
    meter = cost.Meter(log)
    progress = [{"agent": a, "status": "queued", "ms": None} for a in AGENTS]
    cites = Cites()
    sd = get_dict()
    state: dict = {"resume": payload["resume"], "family": payload["job_family"], "posting": payload.get("posting") or ""}
    out: dict = {"result": {"strengths": [], "gaps": [], "recommendations": [], "readiness": {"apply": None, "practice": None}},
                 "notes": []}

    def emit():
        if on_progress:
            on_progress(progress)

    @contextmanager
    def stage(agent: str, llm: bool = False):
        row = next(p for p in progress if p["agent"] == agent)
        row["status"] = "running"
        emit()
        t0 = time.perf_counter()
        meter.start(agent)
        token = bedrock.force_mock("budget") if (llm and meter.over_budget()) else None
        if token is not None:
            row["note"] = "예산 초과 → 규칙 엔진"
        try:
            yield row
            row["status"] = "done"
        except Exception as e:  # noqa: BLE001  한 단계 실패가 전체를 막지 않는다
            row.update(status="failed", note=f"{type(e).__name__}: {str(e)[:120]}")
        finally:
            if token is not None:
                bedrock._force_mock.reset(token)
            meter.stop(agent)
            row["ms"] = round((time.perf_counter() - t0) * 1000)
            emit()

    # guard: 정규식은 접수 때 끝났다. 여기서는 Guardrail(Bedrock 모드)만
    with stage("guard", llm=True) as row:
        masked, n = pii.mask(state["resume"])
        if bedrock.mode() == "bedrock" and GUARDRAIL_ID:
            try:
                masked, n2 = bedrock.guardrail_mask(masked, log=log)
                n += n2
            except bedrock.BedrockError as e:
                row["note"] = f"Guardrail 실패 → 정규식만 ({str(e)[:60]})"
        state["resume"] = masked
        row["masked"] = n

    with stage("star", llm=True) as row:
        strengths, meta = star.diagnose(state["resume"], log=log)
        out["result"]["strengths"] = strengths
        row.update(mode=meta["mode"], dropped_quotes=meta.get("dropped_quotes", 0))
        for e in strengths:
            for k, s in e["slots"].items():
                if s["present"]:
                    s["cite"] = cites.add("resume", "이력서", s["quote"])

    with stage("skills", llm=True) as row:
        if bedrock.mode() == "bedrock":
            try:
                status_map, _ = extract_resume_llm(state["resume"], log=log)
            except bedrock.BedrockError:
                status_map = extract_resume(state["resume"])
                row["note"] = "Bedrock 실패 → 사전"
        else:
            status_map = extract_resume(state["resume"])
        status_map, _ = implies.expand(status_map)
        state["status"] = status_map
        row["n_skills"] = len(status_map)

    with stage("retriever", llm=True) as row:
        status_map = state.get("status", {})
        if state["posting"]:
            reqs = posting_requirements(state["posting"])
            src = "붙여 넣은 공고"
        else:
            reqs, fam = family_apply_requirements(state["family"], status_map)
            src = f"같은 직군({FAMILY_LABEL[state['family']]}) 공개 공고 {fam['n']}건"
        state["reqs"] = reqs
        retr = _optional("retriever")
        practice = None
        if retr and hasattr(retr, "practice_requirements"):
            practice = retr.practice_requirements(state["family"], status_map, log=log)  # T2: NCS 기준 (아직 계약 초안)
        out["result"]["readiness"] = {"apply": readiness(reqs, status_map) if reqs else None,
                                      "practice": readiness(practice, status_map) if practice else None}
        gl = []
        for sid, w, st in score_gaps(reqs, status_map):
            ent = sd.skills.get(sid)
            q = _quote_in(state["posting"], sd.name(sid), (ent or {}).get("aliases", [])) if state["posting"] else None
            n = cites.add("posting", src, q or f"{src}에서 '{sd.name(sid)}'를 {'필수' if w == 2 else '우대'} 기준으로 셈",
                          doc_id=f"posting:{sid}")
            gl.append({"id": sid, "name": sd.name(sid), "status": st, "status_label": STATUS_LABEL[st],
                       "weight": w, "cites": [n]})
        out["result"]["gaps"] = gl
        row.update(source=src, n_requirements=len(reqs), practice="NCS 기준 대기(T2)" if practice is None else "NCS")

    with stage("recommend", llm=True) as row:
        rt = _optional("recommend_task")
        if rt and hasattr(rt, "recommend"):
            recos = rt.recommend(out["result"]["gaps"], out["result"]["strengths"], state["family"], log=log)
            row["impl"] = "T2"
        else:
            recos = _fallback_recommend(out["result"], cites)
            row["impl"] = "임시(규칙)"
        out["result"]["recommendations"] = recos

    with stage("verifier") as row:
        result, alive, rep = verifier.verify(out["result"], cites.items, state["resume"])
        out["result"], out["citations"] = result, alive
        row.update(removed=len(rep["removed"]))
        out["verify"] = rep

    with stage("cost"):
        out["cost"] = meter.summary()
    out["progress"] = progress
    out["trace"] = [{"agent": c["kind"], "model": c["model"], "ms": c["ms"], "in": c["in"], "out": c["out"]} for c in log.calls]
    return out


def _fallback_recommend(result: dict, cites: Cites) -> list[dict]:
    """T2 과제 추천이 들어오기 전 임시: 갭 → 카탈로그 과정 + 결과물 과제, 가장 약한 경험 → STAR 보완 과제."""
    from ..data import courses
    recos = []
    for g in result["gaps"][:MAX_RECO - 1]:
        course, alt = _pick_course(g["id"], "전국")
        c = course or alt
        cn = []
        co = None
        if c:
            cn = [cites.add("course", c["title"], f"{c['provider']} · {c['hours']}시간 · {c['region']}", c.get("url"), c["id"])]
            co = {"id": c["id"], "name": c["title"], "hours": c["hours"], "url": c.get("url")}
        if g["id"] in SOFT:
            task = f"'{g['name']}'이(가) 드러난 경험 하나를 골라 STAR로 다시 쓰기(누구와, 무엇을 조율했고, 결과가 어땠는지)"
        elif g["status"] == "verify":
            task = f"이력서에 '{g['name']}'로 무엇을 했는지 한 문장 이상 쓰기. 없으면 작은 결과물을 만들어 링크"
        else:
            task = f"'{g['name']}'을(를) 직접 써서 작은 결과물을 만들고, README에 상황·과제·행동·결과(숫자)로 정리"
        recos.append({"rank": len(recos) + 1, "target": g["id"],
                      "why": f"지원 기준에 '{g['name']}'이(가) 있으나 이력서 상태는 '{g['status_label']}'",
                      "task": task,
                      "course": co, "cites": g["cites"] + cn, "abstained": False})
    weak = [e for e in result["strengths"] if e["level"] != "strong" and e.get("missing_hint")]
    if weak:
        e = min(weak, key=lambda x: x["score"])
        q = next((s["cite"] for s in e["slots"].values() if s.get("cite")), None)
        recos.append({"rank": len(recos) + 1, "target": f"star:{e['exp_id']}",
                      "why": f"경험 '{e['title']}': {e['missing_hint']}",
                      "task": "이 경험을 STAR로 다시 쓰기: 어떤 문제였고(S), 내가 맡은 것(T), 한 일(A), 바뀐 숫자(R)",
                      "course": None, "cites": [q] if q else [], "abstained": False})
    return recos
