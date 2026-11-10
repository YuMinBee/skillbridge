"""스킬 정규화: 별칭 사전 정확 매칭 → 실패분만 임베딩 top-k 후보 → LLM이 고르거나 none.

스킬 임베딩 인덱스는 처음 한 번 만들어 backend/.data/에 캐시한다 (skills.csv가 바뀌면 다시 만든다).
"""
import hashlib
import json
import math
from functools import lru_cache

from ..adapters import bedrock
from ..config import DB_PATH, EMBED_MODEL_ID, FAST_MODEL_ID, SKILLS_CSV
from ..skills import get_dict

TOP_K = 5
MIN_SIM = 0.05  # 순위가 중요하다: 짧은 한국어 표현은 유사도 절댓값이 낮게 나온다. 최종 판단은 LLM이 한다


def _skill_text(sid: str) -> str:
    sd = get_dict()
    s = sd.skills[sid]
    names = [s["name"]] + [a for a in s.get("aliases", []) if a != s["name"]][:6]
    return f"{' / '.join(names)} · {s['category']}"


@lru_cache(maxsize=1)
def skill_index() -> tuple[list[str], list[list[float]]]:
    sd = get_dict()
    ids = sorted(sd.skills)
    h = hashlib.sha1((SKILLS_CSV.read_bytes() + EMBED_MODEL_ID.encode())).hexdigest()[:12]
    cache = DB_PATH.parent / f"skill_emb_{h}.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d["ids"] == ids:
            return d["ids"], d["vecs"]
    vecs = bedrock.embed([_skill_text(i) for i in ids])
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"ids": ids, "vecs": vecs}), encoding="utf-8")
    return ids, vecs


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / ((math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1)


def candidates(mentions: list[str], log=None) -> list[list[tuple[str, float]]]:
    ids, vecs = skill_index()
    qv = bedrock.embed(mentions, log=log)
    out = []
    for q in qv:
        sims = sorted(((ids[i], _cos(q, v)) for i, v in enumerate(vecs)), key=lambda x: -x[1])
        out.append([(sid, round(s, 3)) for sid, s in sims[:TOP_K] if s >= MIN_SIM])
    return out


_PICK_SYS = """너는 이력서·채용공고에서 뽑힌 기술 표현을 표준 스킬 목록에 연결한다.
각 표현마다 후보 중 같은 기술(또는 그 기술을 직접 포함하는 상위 개념)을 하나 고르고,
맞는 후보가 없으면 skill_id를 "none"으로 한다. 비슷한 분야라는 이유만으로 고르지 않는다."""

_PICK_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"i": {"type": "integer"}, "skill_id": {"type": "string"}},
        "required": ["i", "skill_id"]}}},
    "required": ["items"],
}


def _query(m: dict) -> str:
    std = m.get("standard_name", "").strip()
    return f"{std} / {m['mention']}" if std and std != m["mention"] else m["mention"]


def normalize(mentions: list[dict], log=None, use_embedding=True, use_llm=True) -> list[dict]:
    """mentions: [{mention, standard_name?, evidence, ...}] → 각 항목에 skill_ids, how(dict|dict-std|embed|llm|none) 추가.

    use_embedding/use_llm은 평가(M5 ablation)에서 단계별로 끄기 위한 스위치다.
    """
    sd = get_dict()
    pending = []
    for m in mentions:
        hits = [h["skill_id"] for h in sd.find(m["mention"])]
        how = "dict"
        if not hits and m.get("standard_name"):  # 추출 LLM이 붙인 표준 영문명으로 한 번 더 (예: 쿠베 → Kubernetes)
            hits = [h["skill_id"] for h in sd.find(m["standard_name"])]
            how = "dict-std"
        if hits:
            m["skill_ids"], m["how"] = list(dict.fromkeys(hits)), how
        else:
            m["skill_ids"], m["how"] = [], "none"
            pending.append(m)
    if not pending or not use_embedding:
        return mentions

    cands = candidates([_query(p) for p in pending], log=log)
    if not use_llm:
        for p, c in zip(pending, cands):
            if c and c[0][1] >= 0.3:
                p["skill_ids"], p["how"] = [c[0][0]], "embed"
        return mentions

    lines, ask = [], []
    for i, (p, c) in enumerate(zip(pending, cands)):
        if not c:
            continue
        ask.append(i)
        opts = ", ".join(f"{sid}({sd.name(sid)})" for sid, _ in c)
        std = f" (표준명 추정: {p['standard_name']})" if p.get("standard_name") else ""
        lines.append(f"[{i}] 표현: \"{p['mention']}\"{std} · 문맥: \"{p.get('evidence', '')[:120]}\"\n    후보: {opts}")
    if not ask:
        return mentions
    out = bedrock.converse_tool(_PICK_SYS, "\n".join(lines), "submit_links", _PICK_SCHEMA,
                                model=FAST_MODEL_ID or None, log=log, max_tokens=1500, kind="normalize")
    allowed = {i: {sid for sid, _ in cands[i]} for i in ask}
    for x in out.get("items", []):
        i, sid = x.get("i"), x.get("skill_id")
        if i in allowed and sid in allowed[i]:  # 후보 밖의 ID는 받아들이지 않는다
            pending[i]["skill_ids"], pending[i]["how"] = [sid], "llm"
    return mentions
