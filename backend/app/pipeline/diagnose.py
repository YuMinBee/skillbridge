"""취준생 진단 에이전트: 고정 순서 파이프라인 + 단계별 trace.

BEDROCK_MOCK=0이면 마스킹·추출·공고 기준선·설명을 Bedrock으로 하고, 어느 단계든 실패하면
그 단계만 규칙/템플릿으로 폴백한다 (fallbacks에 사유를 남겨 화면에 표시).
점수와 학습경로는 항상 규칙으로 계산한다 (명세 원칙 4).
"""
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from ..adapters import bedrock, storage
from ..guards import pii
from ..data import seed_companies
from ..skills import get_dict
from . import implies, market, projectfit
from .extract import STATUS_LABEL, extract_posting_llm, extract_resume, extract_resume_llm, posting_requirements, \
    requirements_from
from .recommend import build_path, optimize_order
from .score import FORMULA, WEIGHT_LABEL, gaps, readiness, status_of


class Trace:
    def __init__(self, clog: "bedrock.CallLog | None" = None):
        self.steps = []
        self.clog = clog

    @contextmanager
    def step(self, name: str, tool: str):
        rec = {"name": name, "tool": tool, "detail": ""}
        i0 = len(self.clog.calls) if self.clog else 0
        t0 = time.perf_counter()
        try:
            yield rec
        finally:
            rec["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            if self.clog:
                rec.setdefault("calls", []).extend(self.clog.since(i0))
            self.steps.append(rec)


def effective_requirements(company: dict) -> dict[str, int]:
    ex = set(company.get("excluded", []))
    return {s: w for s, w in company.get("requirements", {}).items() if s not in ex and w in (1, 2)}


def _usage(*logs) -> dict:
    calls = [c for lg in logs if lg for c in lg.calls]
    return {"calls": len(calls),
            "input_tokens": sum(c["in"] for c in calls if c["kind"] != "embed"),
            "output_tokens": sum(c["out"] for c in calls),
            "embed_texts": sum(c["in"] for c in calls if c["kind"] == "embed")}


def run(resume_text: str, company_id: str, weekly_hours: int = 10, log: bool = True) -> dict:
    sd = get_dict()
    mock = bedrock.mode() == "mock"
    clog = None if mock else bedrock.CallLog()
    plog = None if mock else bedrock.CallLog()
    tr = Trace(clog)
    fallbacks: list[str] = [bedrock.forced_reason()] if bedrock.forced_reason() else []
    extraction = None

    company = storage.get_company(company_id)
    if company is None:
        raise KeyError(company_id)

    # 공고 추출은 이력서와 무관하므로 먼저 병렬로 시작한다 (같은 공고 본문은 캐시)
    pool = ThreadPoolExecutor(max_workers=1)
    apply_src = company.get("apply_source", "공고")
    explicit_apply = company.get("apply_requirements")  # 공고가 없는 기업: 현업이 말한 '필수' 항목을 지원 기준으로
    fut_posting = None if (mock or explicit_apply) else pool.submit(extract_posting_llm, company.get("posting_text", ""), plog)

    with tr.step("개인정보 마스킹", "guard.regex_mask" if mock else "guard.regex_mask → bedrock.apply_guardrail(PII)") as s:
        masked, n_pii = pii.mask(resume_text)
        if not mock:
            if not bedrock.GUARDRAIL_ID:
                s["tool"] = "guard.regex_mask (GUARDRAIL_ID 미설정)"
            else:
                try:
                    masked, n_g = bedrock.guardrail_mask(masked, log=clog)
                    n_pii += n_g
                except bedrock.BedrockError as e:
                    fallbacks.append(f"Guardrail: {e}")
                    s["tool"] = "guard.regex_mask (Guardrail 실패 → 폴백)"
        s["detail"] = f"{n_pii}건 가림 · 원문은 저장하지 않음"

    with tr.step("이력서 스킬 추출·정규화",
                 "skills.alias_match" if mock else "bedrock.converse(구조화 출력) → 사전 → 임베딩 top-5 → LLM 선택") as s:
        status_map = None
        if not mock:
            try:
                status_map, extraction = extract_resume_llm(masked, log=clog)
                s["detail"] = (f"{len(status_map)}개 스킬 · 언급 {extraction['mentions']}건 "
                               f"(사전 {extraction['dict']} · 임베딩+LLM {extraction['embed_llm']} · "
                               f"미매칭 {extraction['unmatched']} · 원문에 없는 근거 버림 {extraction['dropped']})")
            except bedrock.BedrockError as e:
                fallbacks.append(f"이력서 추출: {e}")
                s["tool"] = "skills.alias_match (Bedrock 실패 → 폴백)"
        if status_map is None:
            status_map = extract_resume(masked)
            s["detail"] = f"{len(status_map)}개 스킬"

    with tr.step("상하위 스킬 보완", "rules.implies (MySQL → SQL 같은 포함 관계만)") as s:
        status_map, implied = implies.expand(status_map)
        s["detail"] = (", ".join(f"{sd.name(a)} ← {sd.name(b)}" for a, b in implied) or "보완 없음")

    with tr.step("근거 기반 상태 판정",
                 "rules.judge_status" if extraction is None else "LLM 판정(보유/부분/검증 필요) + 원문 근거 대조") as s:
        cnt = {k: sum(1 for v in status_map.values() if v["status"] == k) for k in ("own", "part", "verify")}
        s["detail"] = " · ".join(f"{STATUS_LABEL[k]} {v}" for k, v in cnt.items())

    with tr.step("기업 실무 기준 조회", f"store.get_company(tenant={company_id})") as s:
        reqs = effective_requirements(company)
        s["detail"] = f"{company['name']} · 요구역량 {len(reqs)}개"

    with tr.step("시장 기준 조회", "market.rates(region, job)") as s:
        mrate = market.rate_for_company(company)
        s["detail"] = f"{company.get('region')} · {market.JOBS.get(company.get('job'), '')}"

    with tr.step("공고 지원 기준 조회",
                 "rules.posting_requirements" if mock else "bedrock.converse(공고 구조화 출력, 캐시)") as s:
        preqs = None
        if fut_posting is not None:
            try:
                preqs = requirements_from(fut_posting.result())
                s["calls"] = list(plog.calls)
                if not plog.calls:
                    s["tool"] += " · 캐시 적중"
            except bedrock.BedrockError as e:
                fallbacks.append(f"공고 추출: {e}")
                s["tool"] = "rules.posting_requirements (Bedrock 실패 → 폴백)"
        pool.shutdown(wait=False)
        if explicit_apply:
            preqs = dict(explicit_apply)
            s["tool"] = "company.apply_requirements (현업 인터뷰 필수 항목)"
        if preqs is None:
            preqs = posting_requirements(company.get("posting_text", ""))
        s["detail"] = f"{apply_src} 요구 {len(preqs)}개 (입사 문턱)"

    with tr.step("준비도 계산", "rules.readiness × (공고 지원 기준, 기업 실무 기준)") as s:
        score = readiness(reqs, status_map)
        score_apply = readiness(preqs, status_map)
        s["detail"] = f"지원 {score_apply}점 · 실무 {score}점"

    with tr.step("학습경로 생성",
                 "catalog ∪ corp_track → 지원 기준 갭 먼저 → 실무 기준 갭 → 단계 안에서 greedy(시간당 준비도+시장 적합도)") as s:
        path = build_path(reqs, status_map, company, weekly_hours, apply_reqs=preqs)
        mregion = "dg" if company.get("region") == "대경권" else "all"
        path = optimize_order(path, status_map, reqs, market.posting_requirement_maps(mregion, company.get("job", "ai")),
                              apply_reqs=preqs)
        m = path["market"]
        n_apply = sum(st["tier"] == "apply" for st in path["steps"])
        s["detail"] = (f"{len(path['steps'])}단계(지원 {n_apply} · 실무 {len(path['steps']) - n_apply}) · "
                       f"{path['total_hours']}시간 · 시장 공고 평균 적합도 {m['fit_before']} → {m['fit_after']}점 ({m['postings']}건)")

    with tr.step("지원 기준 vs 실무 기준", "rules.gaps × 2") as s:
        g_post = [g[0] for g in gaps(preqs, status_map)]
        g_corp = [g[0] for g in gaps(reqs, status_map)]
        baseline = {
            "posting_requirements": [{"skill_id": k, "name": sd.name(k), "weight": w, "weight_label": WEIGHT_LABEL[w]}
                                     for k, w in sorted(preqs.items(), key=lambda x: -x[1])],
            "gaps_posting": [{"skill_id": k, "name": sd.name(k), "status": status_of(status_map, k)} for k in g_post],
            "gaps_company": [{"skill_id": k, "name": sd.name(k), "status": status_of(status_map, k)} for k in g_corp],
            "missed": [sd.name(k) for k in g_corp if k not in g_post],
            "unnecessary": [sd.name(k) for k in g_post if k not in g_corp],
            "readiness_posting": score_apply,
            "readiness_company": score,
        }
        s["detail"] = f"입사 후 추가로 필요한 것 {len(baseline['missed'])} · 지원에만 필요한 것 {len(baseline['unnecessary'])}"

    with tr.step("다른 기업과 비교", "rules.readiness × 기업") as s:
        others = []
        for c in storage.list_companies():
            r = effective_requirements(c)
            g = gaps(r, status_map)
            others.append({"company_id": c["tenant_id"], "name": c["name"], "readiness": readiness(r, status_map),
                           "first_task": sd.name(g[0][0]) if g else None, "current": c["tenant_id"] == company_id})
        others.sort(key=lambda x: -x["readiness"])
        s["detail"] = f"{len(others)}개 기업"

    with tr.step("프로젝트 적합도", "rules.projectfit (경험 단위 × 부서 실무 기준 · 도메인 단어)") as s:
        seeds = seed_companies()

        def with_domain(c):  # 로컬 DB에 예전 설정이 남아 있어도 도메인 단어는 seed에서 채운다
            return c if c.get("domain") else {**c, "domain": seeds.get(c["tenant_id"], {}).get("domain")}

        pfit = projectfit.assess(masked, status_map, with_domain(company), reqs)
        for o in others:
            c = storage.get_company(o["company_id"])
            o["project_fit"] = projectfit.best_fit(masked, status_map, with_domain(c), effective_requirements(c))
        s["detail"] = f"경험 {pfit['n_units']}개 · 가장 맞는 경험 {pfit['best_fit']}점 · {pfit['verdict_label']}"

    # 근거 목록: 추천 설명은 이 목록의 ID만 인용할 수 있다
    evidence: dict[str, dict] = {}

    def add_ev(type_, text):
        eid = f"E{len(evidence) + 1}"
        evidence[eid] = {"id": eid, "type": type_, "text": text}
        return eid

    posting_ev = {}
    for line in company.get("posting_text", "").splitlines():
        for m in sd.find(line):
            posting_ev.setdefault(m["skill_id"], line.lstrip("-•· ").strip())

    with tr.step("설명 작성", "template(근거 인용)" if mock else "bedrock.converse(근거 ID 인용만 허용) → 인용 검증") as s:
        ev_by_skill: dict[str, list[str]] = {}
        for st in path["steps"]:
            sid = st["skill_id"]
            if sid not in ev_by_skill:
                ids = []
                if sid in preqs:
                    ids.append(add_ev("apply", f"{company['name']} {apply_src} 지원 기준: {WEIGHT_LABEL[preqs[sid]]}"))
                if sid in reqs:
                    ids.append(add_ev("corp", f"{company['name']} {company.get('work_source', '등록')} 실무 기준: {WEIGHT_LABEL[reqs[sid]]}"))
                if sid in mrate:
                    ids.append(add_ev("market", f"시장 언급률 {mrate[sid]:.0f}% ({company.get('region')})"))
                if sid in status_map:
                    ids.append(add_ev("resume", status_map[sid]["evidence"]))
                if sid in posting_ev:
                    ids.append(add_ev("posting", posting_ev[sid]))
                ev_by_skill[sid] = ids
            st["evidence_ids"] = list(ev_by_skill[sid])
            if st.get("gain"):
                g = st["gain"]
                apply_txt = f"지원 준비도 {g['apply_after']}점(+{g['apply']}), " if g.get("apply_after") is not None else ""
                st["evidence_ids"].append(add_ev("plan", f"이 단계를 마치면 {apply_txt}실무 준비도 {g['readiness_after']}점(+{g['readiness']}), "
                                                          f"시장 공고 평균 적합도 +{g['market_fit']}점 · 시간당 효과 {g['per_hour']}"))
        whys, n_tpl = None, 0
        if not mock and path["steps"]:
            try:
                whys, n_tpl = bedrock.explain_steps(path["steps"], evidence, company["name"], log=clog)
            except bedrock.BedrockError as e:
                fallbacks.append(f"설명: {e}")
                s["tool"] = "template(근거 인용) (Bedrock 실패 → 폴백)"
        if whys is None:
            whys = [bedrock.template_why(st, evidence) for st in path["steps"]]
        for st, w in zip(path["steps"], whys):
            st["why"] = w
        s["detail"] = f"근거 {len(evidence)}건"
        if not mock:
            s["detail"] += f" · 인용 검증 통과 {len(whys) - n_tpl}/{len(whys)}" + (f" · {n_tpl}건 템플릿 대체" if n_tpl else "")

    # 매트릭스: 공고(지원 기준) 스킬 먼저, 그다음 기업 실무 기준에만 있는 스킬
    matrix = []
    rows = sorted(preqs.items(), key=lambda x: (-x[1], x[0])) + \
        sorted(((k, v) for k, v in reqs.items() if k not in preqs), key=lambda x: (-x[1], x[0]))
    for sid, w in rows:
        st = status_of(status_map, sid)
        ev = status_map.get(sid, {}).get("evidence")
        if ev and status_map[sid].get("implied_by"):
            ev = f"{sd.name(status_map[sid]['implied_by'])} 근거로 인정: {ev}"
        tiers = [lab for lab, src in (("지원", preqs), ("실무", reqs)) if sid in src]
        matrix.append({"skill_id": sid, "name": sd.name(sid), "weight": w, "weight_label": WEIGHT_LABEL[w],
                       "tier": "apply" if sid in preqs else "work", "tier_label": "·".join(tiers),
                       "weight_apply": preqs.get(sid), "weight_work": reqs.get(sid),
                       "status": st, "status_label": STATUS_LABEL[st],
                       "evidence": ev or (f"{'공고' if sid in preqs else '기업'} 요구 · 시장 언급률 {mrate.get(sid, 0):.0f}%"
                                          if st == "miss" else "-"),
                       "market_pct": round(mrate.get(sid, 0), 1)})

    if log:
        storage.log_session(company_id, g_corp, {k: v["status"] for k, v in status_map.items()})  # 익명: 상태 코드만

    return {
        "company": {"id": company["tenant_id"], "name": company["name"], "desc": company.get("desc", "")},
        "readiness": score,               # 실무 준비도 (기업 등록 기준)
        "readiness_apply": score_apply,   # 지원 준비도 (공고 기준)
        "formula": FORMULA,
        "skills_found": [{"skill_id": k, "name": sd.name(k), "status": v["status"],
                          "status_label": STATUS_LABEL[v["status"]], "evidence": v["evidence"],
                          "how": v.get("how", "dict-rule")}
                         for k, v in sorted(status_map.items(), key=lambda x: (-["miss", "verify", "part", "own"].index(x[1]["status"]), x[0]))],
        "matrix": matrix,
        "path": path,
        "baseline": baseline,
        "project_fit": pfit,
        "others": others,
        "evidence": evidence,
        "trace": tr.steps,
        "mode": bedrock.mode(),
        "fallbacks": fallbacks,
        "extraction": extraction,
        "usage": None if mock else _usage(clog, plog),
        "pii_masked": n_pii,
    }
