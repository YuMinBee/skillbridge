"""재랭킹. 서울 리전에 Bedrock Rerank 모델이 없어(2026-11-17 확인) Haiku가 관련도 0~3점을 매긴다.
mock 모드나 호출 실패면 순서를 바꾸지 않는다(검색 결과는 그대로 나감)."""
from ..adapters import bedrock
from ..config import FAST_MODEL_ID

_SCHEMA = {"type": "object", "required": ["scores"],
           "properties": {"scores": {"type": "array", "items": {
               "type": "object", "required": ["i", "score"],
               "properties": {"i": {"type": "integer"}, "score": {"type": "integer", "minimum": 0, "maximum": 3}}}}}}
_SYSTEM = ("검색 결과 재랭킹. 질의에 답하는 데 각 후보가 얼마나 직접 쓸모 있는지 0~3으로 매긴다. "
           "3=질의 내용을 직접 다룸, 2=관련 깊음, 1=주제만 비슷, 0=무관. 모든 후보에 점수를 준다.")


def rerank(query: str, hits: list[dict], *, log: bedrock.CallLog | None = None) -> list[dict]:
    if not hits or bedrock.mode() != "bedrock":
        return hits
    cands = "\n".join(f"[{i}] {h['title']} | {h['text'][:600]}" for i, h in enumerate(hits))
    try:
        r = bedrock.converse_tool(_SYSTEM, f"질의: {query}\n\n후보:\n{cands}", "submit_scores", _SCHEMA,
                                  model=FAST_MODEL_ID, log=log, max_tokens=1000, kind="rerank")
    except bedrock.BedrockError:
        return hits
    s = {x["i"]: x["score"] for x in r.get("scores", []) if isinstance(x.get("i"), int)}
    # 같은 점수면 원래 검색 순서 유지 (sorted는 안정 정렬)
    return [h for _, h in sorted(enumerate(hits), key=lambda x: -s.get(x[0], 0))]
