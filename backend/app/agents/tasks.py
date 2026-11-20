"""과제 구체화 (2026-11-20). 템플릿 과제("'AWS'를 직접 써서 작은 결과물을…")를 공고·자소서에 근거한 구체 과제로 바꾼다.

웹 Claude는 "동시성 락을 적용하고 테스트로 증명" 처럼 구체적인 과제를 줬고, 우리 템플릿은 모든 역량에 같은 문장이었다.
- LLM은 과제 문장을 쓰되, 왜 필요한지 보여 줄 **공고 문장**과 확장할 **자소서 문장**을 원문 그대로 함께 낸다.
- 코드가 대조한다: 공고 인용이 그 역량의 공고 근거 안에 있어야 하고, 자소서 인용은 자소서에 있어야 한다.
  과제에 원문에 없는 숫자가 있으면(지어낸 목표·성과) 버린다. 하나라도 어기면 그 역량은 템플릿 과제 그대로.
- 점수·순서는 바꾸지 않는다(규칙 8). 과제 문장만 바뀐다.
"""
import re

from ..adapters import bedrock
from .star import locate

MAX_TASK_CHARS = 180
MAX_RESUME_CHARS = 8000

_SYS = """너는 취업 준비생의 과제 코치다. 부족한 역량마다, 지원자가 혼자 할 수 있는 구체적인 과제 하나를 쓴다.
규칙:
- 과제는 한두 문장, 180자 이내. 무엇을 만들거나 바꾸고, 무엇을 확인·측정하고, 결과를 어디에(README 등) 남길지 구체적으로 쓴다.
- 지원자의 기존 경험을 확장하는 과제를 우선한다. 그때 그 경험의 자소서 문장 하나를 resume_quote에 원문 그대로 복사한다. 맞는 경험이 없으면 resume_quote는 null.
- posting_quote에는 그 역량에 주어진 공고 문장 중 하나를 원문 그대로 복사한다(긴 문장이면 연속된 일부를 그대로 잘라도 된다). 요약하거나 고치지 않는다.
- 지원자가 하지 않은 일을 했다고 쓰지 않는다. 숫자(목표치·기간·성과)를 새로 만들지 않는다. 결과는 '측정해 기록'처럼 쓴다.
- 교육과정·회사 이름을 쓰지 않는다(과정은 따로 붙는다)."""

_SCHEMA = {"type": "object", "properties": {"tasks": {"type": "array", "items": {
    "type": "object", "properties": {
        "target": {"type": "string", "description": "역량 id (입력의 id 그대로)"},
        "task": {"type": "string"},
        "posting_quote": {"type": "string"},
        "resume_quote": {"type": ["string", "null"]}},
    "required": ["target", "task", "posting_quote", "resume_quote"]}}}, "required": ["tasks"]}

# 도구 이름 속 숫자(JUnit5, EC2, k6)는 빼고, 따로 선 숫자(50%, 3배, 1초)만 본다
_NUM = re.compile(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)?(?![A-Za-z0-9])")


def _numbers_ok(task: str, sources: list[str]) -> bool:
    """과제의 숫자는 자소서·공고 근거에 있는 것만 허용한다(지어낸 목표치·성과 차단)."""
    src = " ".join(s for s in sources if s)
    return all(n in src for n in _NUM.findall(task))


def concretize(recos: list[dict], gaps: list[dict], cite_items: list[dict], resume: str, cites, log=None) -> dict:
    """recos를 제자리에서 고친다. → {"asked", "accepted", "rejected": [(target, 이유)]}"""
    by_gap = {g["id"]: g for g in gaps}
    quote_of = {c["n"]: c for c in cite_items}
    todo = []
    for r in recos:
        g = by_gap.get(r.get("target"))
        if not g:
            continue
        posts = [quote_of[n]["quote"] for n in g.get("cites", []) if n in quote_of and quote_of[n]["kind"] == "posting" and quote_of[n].get("quote")]
        if posts and not r["task"].startswith(f"'{g['name']}'이(가) 드러난") and not g["id"].startswith("cert_"):
            todo.append((r, g, posts))
    rep = {"asked": len(todo), "accepted": 0, "rejected": []}
    if not todo:
        return rep
    lines = []
    for r, g, posts in todo:
        lines.append(f"- id: {g['id']} | 역량: {g['name']} | 이력서 상태: {g.get('status_label', '')}\n  공고 문장:\n" +
                     "\n".join(f"    · {p}" for p in posts[:3]))
    user = f"<자소서>\n{resume[:MAX_RESUME_CHARS]}\n</자소서>\n\n<부족한 역량>\n" + "\n".join(lines) + "\n</부족한 역량>"
    out = bedrock.converse_tool(_SYS, user, "submit_tasks", _SCHEMA, log=log, kind="task", max_tokens=3000)
    got = {t.get("target"): t for t in out.get("tasks", []) if isinstance(t, dict)}
    for r, g, posts in todo:
        t = got.get(g["id"])
        why = None
        if not t or not isinstance(t.get("task"), str) or not t["task"].strip():
            why = "응답 없음"
        else:
            task = t["task"].strip()
            pq = t.get("posting_quote") or ""
            rq = t.get("resume_quote") or None
            pq_ok = next((locate(pq, p) for p in posts if locate(pq, p)), None)
            rq_ok = locate(rq, resume) if rq else None
            if len(task) > MAX_TASK_CHARS:
                why = "너무 김"
            elif not pq_ok:
                why = "공고 인용이 공고에 없음"
            elif rq and not rq_ok:
                why = "자소서 인용이 자소서에 없음"
            elif not _numbers_ok(task, [resume, *posts]):
                why = "원문에 없는 숫자"
        if why:
            rep["rejected"].append((g["id"], why))
            rep.setdefault("rejected_text", []).append((g["id"], (t or {}).get("task", "")[:120]))
            continue
        r["task"] = task
        r["task_via"] = "llm"
        r["task_basis"] = {"posting": pq_ok, "resume": rq_ok}
        if rq_ok:
            r["cites"] = r["cites"] + [cites.add("resume", "자기소개서", rq_ok, None, "resume")]
        rep["accepted"] += 1
    return rep
