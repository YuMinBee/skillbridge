"""준비도 점수 (규칙 고정, LLM 사용 금지). 같은 입력이면 항상 같은 점수."""

WEIGHT_LABEL = {2: "필수", 1: "우대"}
STATUS_VALUE = {"own": 1.0, "part": 0.5, "verify": 0.5, "miss": 0.0}
FORMULA = "준비도 = Σ(가중치 × 상태값) / Σ가중치 × 100 · 가중치: 필수 2, 우대 1 · 상태값: 보유 1.0 / 부분 0.5 / 검증 필요 0.5 / 없음 0"


def status_of(status_map: dict[str, dict], sid: str) -> str:
    s = status_map.get(sid)
    return s["status"] if s else "miss"


def readiness(requirements: dict[str, int], status_map: dict[str, dict]) -> int:
    den = sum(requirements.values())
    if den == 0:
        return 0
    num = sum(w * STATUS_VALUE[status_of(status_map, sid)] for sid, w in requirements.items())
    return round(num / den * 100)


def gaps(requirements: dict[str, int], status_map: dict[str, dict]) -> list[tuple[str, int, str]]:
    """보유가 아닌 요구역량. 정렬: 필수 먼저 → 같은 구분 안에서 상태값 낮은 순 → 스킬 ID."""
    g = [(sid, w, status_of(status_map, sid)) for sid, w in requirements.items()
         if status_of(status_map, sid) != "own"]
    g.sort(key=lambda x: (-x[1], STATUS_VALUE[x[2]], x[0]))
    return g


def resolve_any_of(requirements: dict[str, int], groups: list[list[str]] | None, status_map: dict[str, dict]) -> dict[str, int]:
    """'A 또는 B' 요건: 묶음 안에서 가장 잘 갖춘 스킬 하나만 남긴다(동점이면 먼저 적힌 것). 가중치는 묶음의 최댓값."""
    if not groups:
        return requirements
    out = dict(requirements)
    for g in groups:
        members = [s for s in g if s in out]
        if len(members) < 2:
            continue
        best = max(members, key=lambda s: (STATUS_VALUE[status_of(status_map, s)], -members.index(s)))
        w = max(out[s] for s in members)
        for s in members:
            out.pop(s)
        out[best] = w
    return out
