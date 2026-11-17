"""검색 진입점 (CONTRACTS 3절). search()만 밖에서 쓴다.

config = "방식|임베딩|청크전략[|rr]"
  방식: bm25 · dense · hybrid(RRF)    임베딩: t2v256 · t2v512 · t2v1024 (BEDROCK_MOCK이면 mock 해시)
  청크: chunk.STRATEGIES               rr: Haiku 재랭킹 (상위 RERANK_POOL개를 다시 정렬)
"best"는 조합 실험(eval/trust/run_retrieval.py)으로 고른 값. 실험 전에는 임시값.

코퍼스: seed/corpus/*.jsonl(T3) → 없으면 고용24 과정 카탈로그를 kind="course" 문서로 바꿔 쓴다.
"""
import json
from functools import lru_cache

from ..adapters import bedrock
from ..config import SEED
from ..data import courses
from . import chunk, embed_cache
from .bm25 import BM25
from .hybrid import rrf
from .rerank import rerank

BEST = "hybrid|t2v512|struct"  # 임시: 조합 실험 뒤 교체
POOL = 50  # 융합·재랭킹 전에 각 검색기에서 뽑는 후보 수
RERANK_POOL = 20
_EMB = {"t2v256": 256, "t2v512": 512, "t2v1024": 1024}


def _course_doc(c: dict) -> dict:
    ncs = c.get("ncs") or {}
    lines = [c["title"],
             " · ".join(str(x) for x in (c.get("provider"), f"{c.get('hours')}시간", c.get("level"), c.get("region")) if x),
             f"NCS {ncs.get('code', '')} {ncs.get('name', '')}".strip() if ncs else "",
             "스킬: " + ", ".join(c.get("skills", []))]
    return {"doc_id": f"course:{c['id']}", "kind": "course", "title": c["title"],
            "text": "\n".join(x for x in lines if x), "source": c.get("source", "고용24"),
            "url": c.get("link") or c.get("url"), "meta": {"course_id": c["id"]}}


@lru_cache(maxsize=1)
def corpus() -> tuple[dict, ...]:
    files = sorted((SEED / "corpus").glob("*.jsonl"))
    if files:
        return tuple(json.loads(ln) for f in files for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip())
    return tuple(_course_doc(c) for c in courses())


@lru_cache(maxsize=16)
def _index(strategy: str):
    chunks = chunk.chunk_docs(list(corpus()), strategy)
    return chunks, BM25([f"{c['title']} {c['text']}" for c in chunks])


def _model(emb: str) -> tuple[str, int]:
    dims = _EMB[emb]
    return ("mock" if bedrock.mode() != "bedrock" else embed_cache.TITAN), dims


def parse(config: str) -> tuple[str, str, str, bool]:
    p = (BEST if config == "best" else config).split("|")
    method, emb, strategy, rr = p[0], p[1], p[2], "rr" in p[3:]
    if method not in ("bm25", "dense", "hybrid") or emb not in _EMB:
        raise ValueError(f"모르는 검색 설정: {config}")
    return method, emb, strategy, rr


def _top(scores: list[float], ids: list[int], n: int) -> list[int]:
    return sorted(ids, key=lambda i: -scores[i])[:n]


def search(query: str, k: int = 5, *, kinds: list[str] | None = None, job_family: str | None = None,
           config: str = "best", log: bedrock.CallLog | None = None) -> list[dict]:
    """→ [{chunk_id, doc_id, kind, title, url, text, score}] 점수 내림차순.
    job_family: 문서 meta에 직군이 없으면(과정 등 직군 공통) 통과시킨다."""
    method, emb, strategy, rr = parse(config)
    chunks, bm = _index(strategy)
    ids = [i for i, c in enumerate(chunks)
           if (not kinds or c["kind"] in kinds)
           and (not job_family or c["meta"].get("job_family") in (None, job_family))]
    if not ids:
        return []

    runs: list[list[float]] = []  # 검색기별 청크 점수
    if method in ("bm25", "hybrid"):
        runs.append(bm.scores(query))
    if method in ("dense", "hybrid"):
        model, dims = _model(emb)
        try:
            vecs = embed_cache.embed([chunks[i]["text"] for i in ids] + [query], model, dims, log=log)
            qv = vecs.pop()
            # ponytail: 순수 파이썬 내적(전수 검색). 청크가 수만 개가 되면 numpy 또는 KB로
            dense = [0.0] * len(chunks)
            for i, v in zip(ids, vecs):
                dense[i] = sum(a * b for a, b in zip(v, qv))
            runs.append(dense)
        except bedrock.BedrockError:
            if not runs:  # 벡터 검색 실패 → BM25로 대신
                runs.append(bm.scores(query))

    rankings = [_top(s, ids, POOL) for s in runs]
    scored = rrf(rankings) if len(runs) > 1 else [(i, runs[0][i]) for i in rankings[0]]

    hits = [{"chunk_id": chunks[i]["chunk_id"], "doc_id": chunks[i]["doc_id"], "kind": chunks[i]["kind"],
             "title": chunks[i]["title"], "url": chunks[i]["url"], "text": chunks[i]["parent"],
             "score": round(s, 6)} for i, s in scored]
    hits = _best_per_doc(hits)
    if rr:
        head = rerank(query, hits[:RERANK_POOL], log=log)
        hits = [dict(h, score=round(1.0 / (n + 1), 6)) for n, h in enumerate(head)] + hits[RERANK_POOL:]
    return hits[:k]


def _best_per_doc(hits: list[dict]) -> list[dict]:
    """문서 하나당 가장 높은 청크 하나만. 한 문서의 여러 줄(struct)·여러 자식(hier)이 top-k를 다 채우지 않게."""
    seen, out = set(), []
    for h in hits:
        if h["doc_id"] not in seen:
            seen.add(h["doc_id"])
            out.append(h)
    return out
