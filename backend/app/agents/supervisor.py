"""슈퍼바이저. 단계를 계획·실행하고, 한 단계가 실패해도 나머지 결과를 낸다. CONTRACTS.md 5절의 result를 만든다.

단계: guard(개인정보) → star(① 강점) → skills(스킬 추출) → retriever(② 역량 기준) → recommend(③ 과제) → verifier → cost
- ②③은 T2 모듈(agents/retriever.py, agents/recommend_task.py)이 있으면 그것을 쓰고, 없으면 아래 임시 구현을 쓴다.
- 요청 예산(config.JOB_BUDGET_USD)을 넘으면 남은 LLM 단계는 규칙 엔진으로 돈다.
- 이력서 원문은 저장하지 않는다. 결과에는 인용 문장만 남는다(규칙 7).
"""
import importlib
import time
from functools import lru_cache
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
from . import tasks as task_agent

AGENTS = ["collect", "guard", "star", "skills", "retriever", "recommend", "verifier", "cost"]
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


# ── ② 지원 기준: 공개 공고 두 출처를 반반 (T2의 NCS 검색이 들어오면 실무 기준이 추가된다) ──
# private = 민간 IT 회사 공개 채용 공고(seed, 원문·링크 보존) · public = 잡알리오 공공기관 정보통신(NCS) 실공고
# 건수가 많은 잡알리오가 결과를 덮지 않도록 출처별 평균을 따로 낸 뒤 반반으로 합친다.
FAMILY_RE = {"backend": r"개발|전산|정보시스템|소프트웨어|SW|웹|서버|정보화|백엔드",
             "ai_ml": r"인공지능|AI|머신러닝|딥러닝|LLM", "data": r"데이터|통계|분석"}
PUBLIC_MIN = 20                     # 직군에 맞는 잡알리오 공고가 이보다 적으면 정보통신 전체를 기준으로
APPLY_MIN, APPLY_MUST = 0.10, 0.30  # 합친 수요(가중치/2의 평균)가 이 값 이상이면 기준, 이상이면 필수


@lru_cache(maxsize=4)
def _jsonl(name: str) -> tuple:
    import json
    from ..config import SEED
    f = SEED / "market" / name
    return tuple(json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()) if f.exists() else ()


def _gongchae() -> tuple:
    return _jsonl("gongchae_it.jsonl")


@lru_cache(maxsize=1)
def _direct() -> tuple:
    """기업 공식 채용 페이지 직접 수집(규칙: seed/market/direct_it.md). 직군(family)은 사람이 붙인 값이라 그대로 쓴다.
    direct_it*.jsonl을 모두 읽는다(사람마다 파일을 따로 두어 충돌을 피함). 같은 링크는 한 번만."""
    from ..config import SEED
    seen, out = set(), []
    for f in sorted((SEED / "market").glob("direct_it*.jsonl")):
        for d in _jsonl(f.name):
            key = (d.get("url") or d.get("id") or "").rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
    return tuple(out)


def posting_pool(job_family: str) -> dict:
    import re
    from ..data import market_postings
    keys = FAMILIES[job_family]
    hidden = hidden_ids()
    priv = []
    for c in seed_companies().values():
        if c["tenant_id"] in hidden or not c.get("posting_text") or not any(k in family_of(c) for k in keys):
            continue
        priv.append({"title": f"{c['name']} 채용 공고", "text": c["posting_text"],
                     "url": (c.get("public_source") or {}).get("posting_url"),
                     "req": resolve_any_of(c.get("apply_requirements") or posting_requirements(c["posting_text"]),
                                           c.get("any_of") or [], {})})
    pat = re.compile(FAMILY_RE[job_family])
    # 고용24 공채속보(민간 기업 IT 직무, collectors/work24_gongchae.py). 직무명으로 직군을 나눈다
    for g in _gongchae():
        if pat.search(g["position"]):
            priv.append({"title": f"{g['company']} · {g['position']} (고용24 공채속보)", "text": g["text"], "url": g.get("url"),
                         "req": posting_requirements(g["text"]), "end": g.get("end")})
    for d in _direct():
        if d.get("family") == job_family:
            priv.append({"title": f"{d['company']} · {d['position']} (공식 채용 페이지)", "text": d["text"], "url": d.get("url"),
                         "req": posting_requirements(d["text"]), "end": d.get("end")})
    it = [p for p in market_postings() if p.get("job") == "public" and any("정보통신" in n for n in p.get("ncs", []))]
    pub = [p for p in it if pat.search(p["title"] + " " + p.get("text", "")[:400])]
    pub_scope = FAMILY_LABEL[job_family]
    if len(pub) < PUBLIC_MIN:
        pub, pub_scope = it, "정보통신 전체"
    pub = [{"title": f"{p['company']} · {p['title']}", "text": p.get("text", ""), "url": p.get("url"),
            "req": posting_requirements(p.get("text", "")), "end": p.get("end")} for p in pub]
    return {"private": priv, "public": pub, "public_scope": pub_scope}


SECTORS = {"private": "민간 기업", "public": "공공기관"}


def pooled_requirements(pool: dict, sector: str = "private") -> tuple[dict, dict]:
    """고른 분야(민간·공공) 공고만으로 수요(가중치/2의 평균)를 낸다. 두 분야는 요구가 달라 섞지 않는다."""
    rates: dict[str, list[float]] = {}
    srcs = [sector] if pool.get(sector) else []
    for k in srcs:
        tot: dict[str, float] = {}
        for p in pool[k]:
            for sid, w in p["req"].items():
                tot[sid] = tot.get(sid, 0) + w
        for sid, t in tot.items():
            rates.setdefault(sid, []).append(t / (2 * len(pool[k])))
    y = {sid: sum(v) / len(srcs) for sid, v in rates.items()} if srcs else {}
    reqs = {sid: (2 if v >= APPLY_MUST else 1) for sid, v in y.items() if v >= APPLY_MIN}
    return reqs, y


@lru_cache(maxsize=16)
def _pooled(job_family: str, sector: str = "private"):
    pool = posting_pool(job_family)
    return pool, *pooled_requirements(pool, sector)


MIN_FAMILY_POSTINGS = 15  # 공고가 이보다 적은 직군은 기준이 몇 개뿐이라 준비도가 부풀려진다(실측 11-20: 민간 데이터 7건 → 백엔드 지원자가 데이터 1위)


def family_postings(f: str, sector: str = "private") -> int:
    pool, _, _ = _pooled(f, sector)
    return len(pool.get(sector) or [])


def infer_family(status_map: dict, sector: str = "private") -> tuple[str, dict]:
    """이력서 스킬이 각 직군 공고 기준과 얼마나 겹치는지(보유·부분·검증 필요를 가중치로 셈) → 가장 높은 직군.
    점수 = Σ(기준 가중치 × 상태값) / Σ기준 가중치 (준비도와 같은 식). 동점이면 백엔드 → AI·ML → 데이터 순.
    공고가 MIN_FAMILY_POSTINGS건 미만인 직군은 점수는 보여 주되 1위 후보에서 뺀다(모두 부족하면 전부 후보)."""
    scores = {}
    for f in FAMILIES:
        _, reqs, _ = _pooled(f, sector)
        scores[f] = readiness(reqs, status_map) if reqs else 0
    enough = [f for f in FAMILIES if family_postings(f, sector) >= MIN_FAMILY_POSTINGS] or list(FAMILIES)
    best = max(enough, key=lambda f: scores[f])
    return best, scores


class NoInput(ValueError):
    """분석할 글이 없다(사용자에게 그대로 보여 줄 문장)."""


def _cert_status(status_map: dict) -> None:
    """자격증은 이력서에 적혀 있으면 그 자체가 증거다(프로젝트로 쓴 흔적을 요구하지 않는다).
    '검증 필요'(이름만 있음) → 보유. 단 '필기'만 합격이면 부분(실기가 남음).
    실측 2026-11-20: '[자격증] 정보처리기사'가 있는데 '정보처리기사 취득 계획 세우기'를 추천했다."""
    for sid, v in status_map.items():
        if not sid.startswith("cert_") or not isinstance(v, dict) or v.get("status") != "verify":
            continue
        v["status"] = "part" if "필기" in (v.get("evidence") or "") else "own"


# 육각형(역량 축 6개) — 직군마다 스킬 사전 분류(data/skills.csv category)를 6개로 묶는다. 축에 없는 분류는 빼고 계산.
RADAR_AXES = {
    "backend": [("언어", {"언어"}), ("프레임워크·API", {"백엔드", "아키텍처", "프론트엔드"}), ("데이터베이스", {"DB", "데이터"}),
                ("클라우드", {"AWS", "클라우드"}), ("인프라·운영", {"DevOps", "인프라", "컨테이너", "IaC", "운영체제", "모니터링", "보안"}),
                ("협업·자격", {"협업", "자격증", "도구", "디지털기초"})],
    "ai_ml": [("언어", {"언어"}), ("머신러닝", {"머신러닝", "컴퓨터비전", "자연어처리", "음성", "연구"}), ("딥러닝", {"딥러닝"}),
              ("생성형 AI", {"생성형AI", "AI활용"}), ("MLOps·클라우드", {"MLOps", "AWS", "클라우드", "컨테이너", "DevOps", "인프라", "IaC", "모니터링"}),
              ("데이터·협업", {"데이터", "데이터엔지니어링", "DB", "협업", "자격증", "도구"})],
    "data": [("언어", {"언어"}), ("데이터 분석", {"데이터"}), ("데이터 엔지니어링", {"데이터엔지니어링"}), ("데이터베이스", {"DB"}),
             ("클라우드·인프라", {"AWS", "클라우드", "컨테이너", "DevOps", "인프라", "IaC", "모니터링", "운영체제"}),
             ("ML·협업", {"머신러닝", "딥러닝", "생성형AI", "협업", "자격증", "도구"})],
}


def radar(reqs: dict, status_map: dict, family: str) -> list[dict]:
    """축마다 me = 그 축 요구역량만으로 계산한 준비도(readiness와 같은 규칙, 0~100, 요구가 없으면 None),
    need = 공고 요구에서 그 축이 차지하는 가중치 비중(가장 큰 축 = 100). LLM 없이 규칙으로만."""
    sd = get_dict()
    cat = lambda sid: (sd.skills.get(sid) or {}).get("category")  # noqa: E731
    rows = []
    for name, cats in RADAR_AXES.get(family, RADAR_AXES["backend"]):
        sub = {sid: w for sid, w in reqs.items() if cat(sid) in cats}
        rows.append({"axis": name, "me": readiness(sub, status_map) if sub else None, "w": sum(sub.values())})
    top = max((r["w"] for r in rows), default=0) or 1
    return [{"axis": r["axis"], "me": r["me"], "need": round(r["w"] / top * 100)} for r in rows]


def _closed(p: dict, today: str) -> bool:
    """마감일이 오늘(한국 시간)보다 앞이면 True. 마감일이 없거나(상시) 형식을 모르면 False."""
    import re
    e = re.sub(r"\D", "", str(p.get("end") or ""))[:8]
    return len(e) == 8 and e < today


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
    state: dict = {"resume": payload.get("resume", ""), "family": payload["job_family"], "posting": payload.get("posting") or "",
                   "sector": payload.get("sector") if payload.get("sector") in SECTORS else "private"}
    out_sector = {"id": state["sector"], "label": SECTORS[state["sector"]]}
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

    # collect: GitHub 공개 README (job 안에서 읽어 접수 응답을 늦추지 않는다). 실패해도 문서만으로 계속
    if payload.get("github"):
        with stage("collect") as row:
            from ..adapters import github as gh
            try:
                items = gh.readmes(payload["github"])
                row["repos"] = [it["repo"] for it in items]
                if items:
                    state["resume"] = "\n\n".join(filter(None, [state["resume"], gh.as_document(items)]))
                    state["github_urls"] = {it["repo"]: it["url"] for it in items}
            except gh.GithubError as e:
                row["note"] = str(e)
    else:
        progress[:] = [p for p in progress if p["agent"] != "collect"]
    if not payload.get("template") and len((state.get("resume") or "").strip()) < 20:
        # 문서 없이 GitHub만 넣었는데 README를 못 읽은 경우: 빈 글로 '부족한 역량'을 추천하지 않는다(점검 2026-11-20)
        raise NoInput("읽을 내용이 없습니다. GitHub 아이디·레포 주소를 확인하거나 자소서·포트폴리오 문서를 함께 올려 주세요")

    # guard: 정규식은 접수 때 끝났다. 여기서는 Guardrail(Bedrock 모드)만
    with stage("guard", llm=True) as row:
        tpl = payload.get("template")
        if tpl:  # 칸마다 표시를 붙여 한 번에 가린 뒤 다시 나눈다 (Guardrail 호출 1회)
            lines = [f"<<{i}{k}>> {' '.join((e.get(k) or '').split())}" for i, e in enumerate(tpl) for k in ("title", *star.SLOTS)]
            lines.append(f"<<skills>> {' '.join((payload.get('skills') or '').split())}")
            marked = "\n".join(lines)
            text = marked
        else:
            text = state["resume"]
        masked, n = pii.mask(text)
        if bedrock.mode() == "bedrock" and GUARDRAIL_ID:
            try:
                masked, n2 = bedrock.guardrail_mask(masked, log=log)
                n += n2
            except bedrock.BedrockError as e:
                row["note"] = f"Guardrail 실패 → 정규식만 ({str(e)[:60]})"
        if tpl:
            import re as _re
            back = [dict() for _ in tpl]
            skills = ""
            for m in _re.finditer(r"^<<(\d+)(title|S|T|A|R)>> ?(.*)$|^<<skills>> ?(.*)$", masked, _re.M):
                if m.group(4) is not None:
                    skills = m.group(4)
                elif int(m.group(1)) < len(back):
                    back[int(m.group(1))][m.group(2)] = m.group(3)
            state["template"] = back
            state["resume"] = star.compose(back, skills)
        else:
            state["resume"] = masked
        row["masked"] = n

    with stage("star", llm=True) as row:
        if state.get("template"):
            strengths, meta = star.from_template(state["template"], state["resume"]), {"mode": "template"}
        else:
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
        _cert_status(status_map)
        state["status"] = status_map
        row["n_skills"] = len(status_map)

    with stage("retriever", llm=_optional("retriever") is not None) as row:
        from datetime import datetime, timedelta, timezone
        today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")  # 한국 시간(윈도우엔 tzdata가 없어 ZoneInfo 대신 +9 고정)
        status_map = state.get("status", {})
        best, fam_scores = infer_family(status_map, state["sector"])  # 직군마다 공고 기준 준비도 → 강점 직군 순위
        inferred = state["family"] in (None, "", "auto")
        if inferred:
            state["family"] = best
        ranking = [{"id": f, "label": FAMILY_LABEL[f], "score": fam_scores[f], "n_postings": family_postings(f, state["sector"]),
                    "few_postings": family_postings(f, state["sector"]) < MIN_FAMILY_POSTINGS}
                   for f in sorted(FAMILIES, key=lambda f: (family_postings(f, state["sector"]) < MIN_FAMILY_POSTINGS, -fam_scores[f]))]
        out["result"]["job_family"] = {"id": state["family"], "label": FAMILY_LABEL[state["family"]],
                                       "inferred": inferred, "scores": fam_scores, "ranking": ranking}
        out["result"]["sector"] = out_sector
        pool = None
        if state["posting"]:
            reqs = posting_requirements(state["posting"])
            src = "붙여 넣은 공고"
        else:
            pool, reqs, demand = _pooled(state["family"], state["sector"])
            sec = state["sector"]
            src = (f"{FAMILY_LABEL[state['family']]} 민간 IT 기업 공개 채용 공고 {len(pool['private'])}건" if sec == "private" else
                   f"잡알리오 공공기관 정보통신 공고({pool['public_scope']}) {len(pool['public'])}건")
        state["reqs"] = reqs
        retr = _optional("retriever")
        practice = None
        if retr and hasattr(retr, "practice_requirements"):
            practice = retr.practice_requirements(state["family"], status_map, log=log)  # T2: NCS 기준 (아직 계약 초안)
        out["result"]["readiness"] = {"apply": readiness(reqs, status_map) if reqs else None,
                                      "practice": readiness(practice, status_map) if practice else None}
        out["result"]["radar"] = radar(reqs, status_map, state["family"]) if reqs else []  # 육각형(화면 Overview)
        gl = []
        for sid, w, st in score_gaps(reqs, status_map):
            ent = sd.skills.get(sid)
            aliases = (ent or {}).get("aliases", [])
            if state["posting"]:
                q = _quote_in(state["posting"], sd.name(sid), aliases)
                n = cites.add("posting", src, q or f"붙여 넣은 공고에서 '{sd.name(sid)}' 언급", doc_id=f"posting:{sid}")
                ns = [n]
            else:
                ns = []
                # 실제 공고 문장 1개 인용. 마감되지 않은 공고를 먼저 고른다(마감 공고 링크는 닫힌 페이지일 수 있음).
                # 집계(준비도·육각형·공고 수)에는 마감 공고도 그대로 둔다. 마감 공고밖에 없으면 제목에 표시
                for p in sorted(pool[sec], key=lambda p: _closed(p, today)):
                    if sid in p["req"]:
                        q = _quote_in(p["text"], sd.name(sid), aliases)
                        if q:
                            title = p["title"] + (" · 마감된 공고" if _closed(p, today) else "")
                            ns.append(cites.add("posting", title, q, p["url"], doc_id=p["url"] or p["title"]))
                            break
                hit = sum(1 for p in pool[sec] if sid in p["req"])
                ns.append(cites.add("posting_stats", "공고 집계",
                                    f"{SECTORS[sec]} 공고 {len(pool[sec])}건 중 {hit}건이 '{sd.name(sid)}'를 요구 "
                                    f"(수요 {demand[sid]:.2f})", doc_id=f"stats:{sec}:{sid}"))
            gl.append({"id": sid, "name": sd.name(sid), "status": st, "status_label": STATUS_LABEL[st],
                       "weight": w, "cites": ns})
        out["result"]["gaps"] = gl
        row.update(source=src, n_requirements=len(reqs), practice="NCS 기준 대기(T2)" if practice is None else "NCS")

    with stage("recommend", llm=True) as row:
        rt = _optional("recommend_task")
        if rt and hasattr(rt, "recommend"):
            recos = rt.recommend(out["result"]["gaps"], out["result"]["strengths"], state["family"], log=log)
            row["impl"] = "T2"
        else:
            recos = _fallback_recommend(out["result"], cites, log=log)
            row["impl"] = "규칙 + 과제 구체화"
            if bedrock.mode() == "bedrock":  # 예산 초과면 stage가 mock으로 돌려 여기를 건너뛴다 → 템플릿 과제
                try:
                    rep = task_agent.concretize(recos, out["result"]["gaps"], cites.items, state["resume"], cites, log=log)
                    row.update(tasks_asked=rep["asked"], tasks_accepted=rep["accepted"],
                               tasks_rejected=[f"{t}: {w}" for t, w in rep["rejected"]])
                except bedrock.BedrockError as e:
                    row["note"] = f"과제 구체화 실패 → 템플릿: {str(e)[:80]}"
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


# 벡터 검색 1위 유사도가 이보다 낮으면 '맞는 과정 없음'으로 추천하지 않는다(엉뚱한 과정보다 거부).
# 근거: eval/trust/abstain_threshold.py — 판정된 질의 40개의 1위 과정 중, 0.34~0.353 사이 기준이면 무관 1위 1개만 빠지고
# 관련 1위는 하나도 잃지 않는다(추천 중 무관 7.5% → 5.1%, 추천 비율 97.5%). 그 구간 안의 0.35를 쓴다. Cohere v4 점수 기준.
MIN_COURSE_SCORE = 0.35


def find_course(name: str, log=None) -> dict | None:
    """부족한 역량 → 고용24 과정 (RAG). Bedrock 모드는 실험으로 고른 조합(rag.retrieve.BEST), 아니면 키워드(BM25).
    앞으로 개강하는 과정만. 벡터 검색 1위가 MIN_COURSE_SCORE 미만이면 {"abstained": True, "score"}(추천하지 않음).
    검색 결과가 없으면 None(기존 카탈로그 규칙으로)."""
    from ..rag import retrieve as R
    vector = bedrock.mode() == "bedrock"
    try:
        hits = R.search(name, 1, config="best" if vector else "bm25", kinds=["course"], log=log)
    except bedrock.BedrockError:
        vector = False
        hits = R.search(name, 1, config="bm25", kinds=["course"])
    if hits:
        h = hits[0]
        if vector and R.BEST.startswith("vector:") and h["score"] < MIN_COURSE_SCORE:
            return {"abstained": True, "score": round(h["score"], 3), "nearest": h["title"]}
        m = h.get("meta", {})
        return {"id": h["doc_id"], "title": h["title"], "provider": m.get("provider", ""), "url": h.get("url"),
                "hours": m.get("hours"), "start": m.get("start"), "end": m.get("end"), "region": m.get("region", ""),
                "via": "rag", "score": round(h["score"], 3)}
    return None


def _fallback_recommend(result: dict, cites: Cites, log=None) -> list[dict]:
    """T2 과제 추천이 들어오기 전 임시: 갭 → 고용24 과정(RAG 검색) + 결과물 과제, 가장 약한 경험 → STAR 보완 과제."""
    recos = []
    for g in result["gaps"][:MAX_RECO - 1]:
        # 과정을 붙이지 않는 경우: 이름만 있는 역량(입문 과정 대신 증거 남기기), 소프트 스킬(IT 과정 코퍼스에 맞는 과정이 없어
        # 엉뚱한 과정이 뽑힌다. 실측 2026-11-20: '커뮤니케이션' → 'C 프로그래밍'). 소프트 스킬은 STAR 다시 쓰기 과제만 낸다.
        no_course = g["status"] == "verify" or g["id"] in SOFT
        c = None if no_course else find_course(g["name"], log=log)
        course_note = None
        if c and c.get("abstained"):  # 맞는 과정이 없다고 판단 → 옛 카탈로그로 채우지 않는다
            course_note = f"고용24 정보기술 과정 중 맞는 과정 없음 (가장 가까운 과정 유사도 {c['score']} < 기준 {MIN_COURSE_SCORE})"
            c = None
        elif c is None and not no_course:
            course, alt = _pick_course(g["id"], "전국")
            c = course or alt
        cn = []
        co = None
        if c:
            when = f"{c['start']} 개강" if c.get("start") else (f"{c['hours']}시간" if c.get("hours") else "")
            cn = [cites.add("course", c["title"], " · ".join(x for x in [c.get("provider"), when, c.get("region")] if x),
                            c.get("url") or c.get("link"), c["id"])]
            co = {"id": c["id"], "name": c["title"], "hours": c.get("hours"), "start": c.get("start"),
                  "url": c.get("url") or c.get("link")}
        if g["id"].startswith("cert_") and g["status"] == "part":
            task = f"'{g['name']}' 실기 시험 일정을 확인하고 준비 계획 세우기 (필기만 합격, 공고에서 요구하는 자격증)"
        elif g["id"].startswith("cert_"):
            task = f"'{g['name']}' 시험 일정을 확인하고 취득 계획 세우기 (공고에서 요구하는 자격증)"
        elif g["id"] in SOFT:
            task = f"'{g['name']}'이(가) 드러난 경험 하나를 골라 STAR로 다시 쓰기(누구와, 무엇을 조율했고, 결과가 어땠는지)"
        elif g["status"] == "verify":
            task = f"이력서에 '{g['name']}'로 무엇을 했는지 한 문장 이상 쓰기. 없으면 작은 결과물을 만들어 링크"
        else:
            task = f"'{g['name']}'을(를) 직접 써서 작은 결과물을 만들고, README에 상황·과제·행동·결과(숫자)로 정리"
        recos.append({"rank": len(recos) + 1, "target": g["id"],
                      "why": f"지원 기준에 '{g['name']}'이(가) 있으나 이력서 상태는 '{g['status_label']}'",
                      "task": task,
                      "course": co, "course_note": course_note, "cites": g["cites"] + cn, "abstained": False})
    weak = [e for e in result["strengths"] if e["level"] != "strong" and e.get("missing_hint")
            and any(s.get("cite") for s in e["slots"].values())]  # 인용할 문장이 있는 경험만 (근거 없는 추천 방지)
    if weak:
        e = min(weak, key=lambda x: x["score"])
        q = next((s["cite"] for s in e["slots"].values() if s.get("cite")), None)
        recos.append({"rank": len(recos) + 1, "target": f"star:{e['exp_id']}",
                      "why": f"경험 '{e['title']}': {e['missing_hint']}",
                      "task": "이 경험을 STAR로 다시 쓰기: 어떤 문제였고(S), 내가 맡은 것(T), 한 일(A), 바뀐 숫자(R)",
                      "course": None, "cites": [q] if q else [], "abstained": False})
    return recos
