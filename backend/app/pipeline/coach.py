"""학습 코치 에이전트: 진단 결과를 두고 묻는 질문에, 모델이 도구를 골라 근거를 모은 뒤 답한다.

- 도구는 5개: 기업 기준 조회 · 과정 검색 · 시장 통계 · 기업 문서(KB) 검색 · 학습 후 준비도 계산
- **tenant는 요청에서 고정**된다. 모델은 도구 인자로 회사를 바꿀 수 없다 (KB 필터도 kb.retrieve 안에서 강제).
- 과정은 도구가 돌려준 카탈로그 항목만 [C:과정ID]로 인용할 수 있다. 결과에 없는 ID를 쓰면 지우고 기록한다.
- 점수는 도구(규칙)로만 계산한다. 모델은 점수를 만들지 않는다.
- 입력은 스킬 상태 코드뿐이다. 이력서 원문은 받지도 저장하지도 않는다.
- MOCK이면 질문 키워드로 도구를 고르는 규칙 플래너가 같은 도구를 같은 형식으로 부른다.
"""
import json
import re
import time

from ..adapters import bedrock, kb, storage
from ..data import courses
from ..skills import get_dict
from . import market
from .diagnose import effective_requirements
from .extract import posting_requirements
from .recommend import LONG_HOURS, _rank
from .score import STATUS_VALUE, WEIGHT_LABEL, gaps, readiness

MAX_TURNS = 5
_CITE_C = re.compile(r"\[C:([A-Za-z0-9_.\-]+)\]")


class Ctx:
    def __init__(self, company: dict, statuses: dict[str, str]):
        self.company = company
        self.tid = company["tenant_id"]
        self.reqs = effective_requirements(company)
        self.status_map = {k: {"status": v} for k, v in statuses.items()}
        self.seen_courses: dict[str, dict] = {}
        self.calls: list[dict] = []


# ---------------------------------------------------------------- 도구
def t_company_criteria(ctx: Ctx) -> dict:
    sd = get_dict()
    preqs = posting_requirements(ctx.company.get("posting_text", ""))
    return {"company": ctx.company["name"],
            "apply_requirements": [{"skill_id": s, "name": sd.name(s), "weight": WEIGHT_LABEL[w],
                                    "my_status": ctx.status_map.get(s, {}).get("status", "miss")} for s, w in preqs.items()],
            "apply_readiness_now": readiness(preqs, ctx.status_map),
            "requirements": [{"skill_id": s, "name": sd.name(s), "weight": WEIGHT_LABEL[w],
                              "my_status": ctx.status_map.get(s, {}).get("status", "miss")}
                             for s, w in sorted(ctx.reqs.items(), key=lambda x: (-x[1], x[0]))],
            "tracks": [{"title": t["title"], "hours": t["hours"], "skills": [sd.name(s) for s in t["skills"]]}
                       for t in ctx.company.get("tracks", [])],
            "readiness_now": readiness(ctx.reqs, ctx.status_map)}


def t_search_courses(ctx: Ctx, skill_id: str, max_hours: int = LONG_HOURS) -> dict:
    sd = get_dict()
    if not sd.exists(skill_id):
        return {"error": f"사전에 없는 스킬: {skill_id}"}
    region = ctx.company.get("region", "")
    cands = sorted((c for c in courses() if skill_id in c["skills"] and c["hours"] <= max_hours), key=_rank(region, skill_id))[:3]
    tracks = [t for t in ctx.company.get("tracks", []) if skill_id in t["skills"]]
    out = []
    for c in cands:
        ctx.seen_courses[c["id"]] = c
        out.append({"course_id": c["id"], "title": c["title"], "provider": c["provider"], "hours": c["hours"],
                    "region": c["region"], "start": c.get("start"), "level": c["level"]})
    return {"skill": sd.name(skill_id), "courses": out,
            "company_tracks": [{"title": t["title"], "hours": t["hours"]} for t in tracks],
            "note": None if out else "카탈로그에 이 스킬 과정이 없습니다 (자습 + 결과물로 증명 권장)"}


def t_market_stats(ctx: Ctx, skill_id: str) -> dict:
    sd = get_dict()
    if not sd.exists(skill_id):
        return {"error": f"사전에 없는 스킬: {skill_id}"}
    rates = market.rate_for_company(ctx.company)
    ranked = sorted(rates.items(), key=lambda x: -x[1])
    rank = next((i + 1 for i, (s, _) in enumerate(ranked) if s == skill_id), None)
    return {"skill": sd.name(skill_id), "scope": f"{ctx.company.get('region')} · {market.JOBS.get(ctx.company.get('job'), '')}",
            "mention_pct": round(rates.get(skill_id, 0), 1), "rank": rank, "of": len(ranked)}


def t_company_docs(ctx: Ctx, query: str) -> dict:
    hits = kb.retrieve(ctx.tid, query[:300], k=3)  # tenant 필터 강제
    return {"mode": kb.mode(), "results": [{"text": h["text"][:400], "source": h["source"]} for h in hits]}


def t_readiness_after(ctx: Ctx, skill_ids: list[str]) -> dict:
    sd = get_dict()
    ids = [s for s in skill_ids if sd.exists(s)][:8]
    after = dict(ctx.status_map)
    for s in ids:
        after[s] = {"status": "own"}
    return {"learn": [sd.name(s) for s in ids], "readiness_now": readiness(ctx.reqs, ctx.status_map),
            "readiness_after": readiness(ctx.reqs, after), "formula": "준비도 = Σ(가중치×상태값)/Σ가중치×100 (규칙)"}


TOOLS = {
    "get_company_criteria": (t_company_criteria, "목표 기업의 공고 지원 기준(입사 문턱)과 기업이 등록한 실무 기준(입사 후 쓰는 역량), 내 상태, 교육 트랙, 지원·실무 준비도",
                             {"type": "object", "properties": {}}),
    "search_courses": (t_search_courses, "스킬 하나에 대한 공공 훈련과정(고용24 카탈로그) 최대 3개와 기업 트랙",
                       {"type": "object", "properties": {"skill_id": {"type": "string"},
                                                         "max_hours": {"type": "integer"}}, "required": ["skill_id"]}),
    "market_stats": (t_market_stats, "그 기업 지역·직무 공고에서 스킬 언급률과 순위",
                     {"type": "object", "properties": {"skill_id": {"type": "string"}}, "required": ["skill_id"]}),
    "company_docs": (t_company_docs, "목표 기업의 내부 문서(온보딩·기술 스택 등)에서 관련 문단 검색",
                     {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    "readiness_after": (t_readiness_after, "스킬들을 보유로 만들면 실무 준비도(기업 기준)가 몇 점이 되는지 (규칙 계산)",
                        {"type": "object", "properties": {"skill_ids": {"type": "array", "items": {"type": "string"}}},
                         "required": ["skill_ids"]}),
}


def call_tool(ctx: Ctx, name: str, args: dict) -> dict:
    t0 = time.perf_counter()
    fn = TOOLS.get(name, (None,))[0]
    if fn is None:
        out = {"error": f"없는 도구: {name}"}
    else:
        args = {k: v for k, v in (args or {}).items() if k in TOOLS[name][2].get("properties", {})}
        try:
            out = fn(ctx, **args)
        except TypeError as e:
            out = {"error": f"인자 오류: {e}"}
    ctx.calls.append({"tool": name, "args": args, "ms": round((time.perf_counter() - t0) * 1000, 1),
                      "summary": _summ(name, out)})
    return out


def _summ(name: str, out: dict) -> str:
    if "error" in out:
        return out["error"]
    if name == "search_courses":
        return f"{out['skill']} 과정 {len(out['courses'])}개 · 기업 트랙 {len(out['company_tracks'])}개"
    if name == "market_stats":
        return f"{out['skill']} 언급률 {out['mention_pct']}% ({out['rank'] or '-'}위/{out['of']})"
    if name == "company_docs":
        return f"문서 {len(out['results'])}건 ({out['mode']})"
    if name == "readiness_after":
        return f"{', '.join(out['learn'])} → {out['readiness_now']}점 → {out['readiness_after']}점"
    return f"요구역량 {len(out['requirements'])}개 · 현재 {out['readiness_now']}점"


# ---------------------------------------------------------------- Bedrock 루프
_SYS = """너는 취업 준비생의 학습 코치다. 목표 기업은 {company}로 고정이다.
규칙:
- 답하기 전에 필요한 도구를 불러 근거를 모은다. 도구 결과에 없는 사실·숫자·과정·회사 이름을 만들지 않는다.
- 과정을 추천할 때는 search_courses 결과의 과정만, 제목 뒤에 [C:과정ID]를 붙인다.
- 점수는 readiness_after/get_company_criteria 결과 숫자만 쓴다. 합격 가능성은 판단하지 않는다.
- 공고 기준은 입사 문턱, 실무 기준은 입사 후 쓰는 역량이다. 순서를 물으면 지원 기준 갭을 먼저 권한다.
- 한국어 해요체, 5문장 이내의 평문. 마크다운(**, #, 목록 기호)을 쓰지 않는다. 마지막에 다음 행동 하나를 제안한다.
- 무엇을 먼저 할지 물으면 readiness_after로 후보별 점수를 계산해 비교한 뒤 답한다.
- 스킬 ID 목록: {skills}"""


def _bedrock_answer(ctx: Ctx, question: str, log: bedrock.CallLog) -> str:
    sd = get_dict()
    skills = ", ".join(f"{s}({sd.name(s)})" for s in sorted(set(ctx.reqs) | set(ctx.status_map)))
    system = _SYS.format(company=ctx.company["name"], skills=skills)
    tools = [{"name": n, "description": d, "inputSchema": {"json": s}} for n, (_, d, s) in TOOLS.items()]
    msgs = [{"role": "user", "content": [{"text": question}]}]
    for _ in range(MAX_TURNS):
        m = bedrock.converse_turn(system, msgs, tools, log=log)
        msgs.append(m)
        uses = [c["toolUse"] for c in m["content"] if "toolUse" in c]
        if not uses:
            return "".join(c.get("text", "") for c in m["content"]).strip()
        msgs.append({"role": "user", "content": [
            {"toolResult": {"toolUseId": u["toolUseId"], "content": [{"json": call_tool(ctx, u["name"], u.get("input", {}))}]}}
            for u in uses]})
    raise bedrock.BedrockError(f"도구 호출이 {MAX_TURNS}턴 안에 끝나지 않음")


# ---------------------------------------------------------------- 규칙 플래너 (MOCK·폴백)
_KW = {
    "courses": ("과정", "강의", "교육", "배우", "수업", "학원", "부트캠프"),
    "market": ("시장", "공고", "수요", "많이", "트렌드", "인기"),
    "docs": ("회사", "업무", "실제", "현업", "팀", "온보딩", "문서", "어떤 일"),
    "order": ("먼저", "순서", "우선", "뭐부터", "무엇부터", "가장", "효과"),
}


def _mentioned_skill(ctx: Ctx, q: str) -> str | None:
    hits = [h["skill_id"] for h in get_dict().find(q)]
    return hits[0] if hits else None


def _rule_answer(ctx: Ctx, question: str) -> str:
    sd = get_dict()
    want = {k for k, kws in _KW.items() if any(w in question for w in kws)} or {"order", "courses"}
    crit = call_tool(ctx, "get_company_criteria", {})
    g = gaps(ctx.reqs, ctx.status_map)
    target = _mentioned_skill(ctx, question) or (g[0][0] if g else None)
    lines = [f"{crit['company']} 기준 지원 준비도(공고)는 {crit['apply_readiness_now']}점, 실무 준비도(기업 등록)는 {crit['readiness_now']}점이에요."]
    if not target:
        return lines[0] + " 등록된 요구역량 기준 갭이 없어요. 결과물(포트폴리오)로 보유 역량을 증명해 보세요."
    apply_gaps = sorted((r for r in crit["apply_requirements"] if r["my_status"] != "own"),
                        key=lambda r: r["weight"] != "필수")
    if "order" in want and apply_gaps:  # 입사 문턱(공고) 갭이 먼저
        target = _mentioned_skill(ctx, question) or apply_gaps[0]["skill_id"]
        lines.append(f"먼저 공고 지원 기준에서 {', '.join(r['name'] + '(' + r['weight'] + ')' for r in apply_gaps[:3])}가 "
                     f"비어 있어요. 입사 문턱이라 이것부터 채우는 게 좋아요.")
    if "order" in want and g:
        after = [(sid, w, call_tool(ctx, "readiness_after", {"skill_ids": [sid]})["readiness_after"]) for sid, w, _ in g[:6]]
        best = max(after, key=lambda x: (x[2], x[1]))  # 동점이면 필수 먼저 (g 순서 유지)
        if not apply_gaps:
            target = _mentioned_skill(ctx, question) or best[0]
        lines.append(f"{'그다음 ' if apply_gaps else ''}입사 후 실무 기준에서는 {sd.name(best[0])}({WEIGHT_LABEL[best[1]]})가 "
                     f"실무 준비도를 가장 많이 올려요: {crit['readiness_now']}점 → {best[2]}점.")
    if "market" in want:
        m = call_tool(ctx, "market_stats", {"skill_id": target})
        lines.append(f"{m['scope']} 공고에서 {m['skill']} 언급률은 {m['mention_pct']}%예요.")
    if "docs" in want:
        d = call_tool(ctx, "company_docs", {"query": f"{sd.name(target)} 업무"})
        if d["results"]:
            lines.append(f"회사 문서에는 이렇게 나와요: “{d['results'][0]['text'][:120]}”")
    if "courses" in want or "order" in want:
        c = call_tool(ctx, "search_courses", {"skill_id": target})
        if c["courses"]:
            x = c["courses"][0]
            lines.append(f"{c['skill']}는 {x['title']} [C:{x['course_id']}] ({x['provider']}, {x['hours']}시간)부터 들어 보세요.")
        elif c["company_tracks"]:
            lines.append(f"{c['skill']}는 공공 과정이 없어 기업 트랙 '{c['company_tracks'][0]['title']}'이 가장 빨라요.")
        else:
            lines.append(f"{c['skill']}는 카탈로그에 과정이 없어요. 자습 후 작은 결과물로 증명해 보세요.")
    return " ".join(lines)


# ---------------------------------------------------------------- 진입점
def _check_cites(ctx: Ctx, answer: str) -> tuple[str, list[str]]:
    bad = [cid for cid in _CITE_C.findall(answer) if cid not in ctx.seen_courses]
    for cid in bad:
        answer = answer.replace(f"[C:{cid}]", "")
    return answer, bad


def run(company_id: str, question: str, statuses: dict[str, str]) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        raise KeyError(company_id)
    sd = get_dict()
    statuses = {k: v for k, v in statuses.items() if sd.exists(k) and v in STATUS_VALUE}
    ctx = Ctx(company, statuses)
    mode, fallbacks, log = bedrock.mode(), [], bedrock.CallLog()
    if bedrock.forced_reason():
        fallbacks.append(bedrock.forced_reason())
    answer = None
    if mode == "bedrock":
        try:
            answer = _bedrock_answer(ctx, question, log)
        except bedrock.BedrockError as e:
            fallbacks.append(f"코치: {e}")
    if not answer:
        mode = "rules" if mode == "bedrock" else "mock"
        answer = _rule_answer(ctx, question)
    answer = re.sub(r"\*\*|__|^#+\s*", "", answer, flags=re.M)  # 화면은 평문
    answer, bad = _check_cites(ctx, answer)
    if bad:
        fallbacks.append(f"도구 결과에 없는 과정 인용 {len(bad)}건 삭제")
    cited = [ctx.seen_courses[c] for c in dict.fromkeys(_CITE_C.findall(answer))]
    return {"answer": answer, "mode": mode, "tool_calls": ctx.calls, "fallbacks": fallbacks,
            "courses": [{"id": c["id"], "title": c["title"], "provider": c["provider"], "hours": c["hours"],
                         "link": c.get("link")} for c in cited],
            "usage": {"calls": len(log.calls), "tokens": sum(c["in"] + c["out"] for c in log.calls)} if log.calls else None}


def to_json(x) -> str:  # 디버그용
    return json.dumps(x, ensure_ascii=False, indent=1)
