"""연결되는 경험: 공고 단어로 쓰지 않은 이력서도 제대로 읽는다.

지금까지는 이력서에 그 기술 이름이 없으면 '없음(0)'이었다. 공고 단어로 이력서를 쓴 사람만 점수가 잘 나온다.
비어 있는 요구 기술마다 두 가지를 본다. 점수는 그대로 규칙(score.py)으로 계산하고, 인정은 최대 0.5까지다.

1) 비슷한 도구 (규칙): 서로 대체되는 도구를 '보유'했으면 → 부분(0.5).  예: MySQL 보유 → PostgreSQL
   - 명백한 대체 관계만 둔다. 부분·검증 필요인 도구로는 올리지 않는다.
2) 경험 연결 (Bedrock): 개념 스킬(extract.INFERABLE)만, 그 일을 직접 해 본 이력서 문장을 그대로 인용하면 → 검증 필요(0.5).
   예: "주문 이벤트를 큐로 비동기 처리" → MSA.  도구 이름(Kubernetes 등)은 경험으로 추측하지 않는다.
   - 인용 문장이 원문에 없으면 버린다. 확신이 없으면 넣지 않도록 지시한다.
"""
from ..adapters import bedrock
from .extract import INFERABLE, _locate

SIMILAR: list[list[str]] = [
    ["mysql", "postgresql", "oracle_db"],
    ["mongodb", "aws_dynamodb"],
    ["aws", "gcp", "azure", "ncp"],
    ["jenkins", "github_actions", "gitlab_ci"],
    ["pytorch", "tensorflow", "keras", "jax"],
    ["fastapi", "flask", "django"],
    ["java", "kotlin"],
    ["javascript", "typescript"],
    ["react", "vue"],
    ["terraform", "aws_cloudformation"],
    ["datadog", "prometheus", "grafana"],
    ["langchain", "llamaindex"],
]
_GROUP = {s: g for g in SIMILAR for s in g}
MAX_LINK = 12  # 한 번에 연결을 찾는 스킬 수 (필수·실무 중요도 순)

_SYS = """너는 채용 담당자다. 이력서에 아래 역량의 이름은 없지만, 지원자가 그 역량으로 하는 일을 이미 직접 해 본 근거가 있는지 찾는다.
- 인정: 그 역량이 다루는 바로 그 일을 본인이 직접 수행했다는 문장.
  예) "주문 이벤트를 큐로 받아 비동기로 처리함" → MSA,  "API 응답 시간을 측정하고 병목 쿼리를 고침" → 성능 최적화
- 불인정: 단어만 비슷함, 다른 분야의 일, 공부·관심·계획만 있음, 여러 단계를 건너뛴 추측.
- 확신이 없으면 넣지 않는다. 대부분의 역량은 연결 근거가 없는 것이 정상이다.
- evidence: 이력서 문장을 한 글자도 바꾸지 말고 그대로 복사한다. reason: 왜 연결되는지 한 문장."""


def _schema(ids):
    return {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "skill_id": {"type": "string", "enum": ids}, "evidence": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["skill_id", "evidence", "reason"]}}}, "required": ["items"]}


def similar(status_map: dict, targets: list[str]) -> tuple[dict, list[tuple[str, str]]]:
    """비어 있는 대상 스킬 중 대체 도구를 보유한 것 → 부분. 입력은 바꾸지 않는다."""
    out, added = dict(status_map), []
    for sid in targets:
        if sid in out:
            continue
        have = [s for s in _GROUP.get(sid, []) if s != sid and out.get(s, {}).get("status") == "own"]
        if have:
            src = out[have[0]]
            out[sid] = {"status": "part", "evidence": src.get("evidence", ""), "similar_to": have[0], "how": "similar"}
            added.append((sid, have[0]))
    return out, added


def link(resume: str, status_map: dict, targets: list[str], names: dict[str, str], log=None) -> tuple[dict, list[dict]]:
    """비어 있는 개념 스킬에 이력서 경험을 연결한다 (Bedrock). → (상태표, [{skill_id, evidence, reason}])"""
    ids = [s for s in targets if s not in status_map and s in INFERABLE][:MAX_LINK]
    if not ids:
        return status_map, []
    lst = "\n".join(f"- {s}: {names.get(s, s)}" for s in ids)
    res = bedrock.converse_tool(_SYS, f"<역량>\n{lst}\n</역량>\n<이력서>\n{resume}\n</이력서>", "submit_bridges", _schema(ids),
                                model=bedrock.FAST_MODEL_ID or None, log=log, kind="link", max_tokens=2000)
    out, links = dict(status_map), []
    for it in res.get("items", []):
        sid = it.get("skill_id")
        if sid not in ids or sid in out:
            continue
        ev = _locate(it.get("evidence", ""), "", resume)  # 원문에 그 문장이 없으면 버린다
        if not ev:
            continue
        out[sid] = {"status": "verify", "evidence": ev, "linked": it.get("reason", "").strip(), "how": "link"}
        links.append({"skill_id": sid, "evidence": ev, "reason": it.get("reason", "").strip()})
    return out, links
