"""검색 (CONTRACTS 3절). 키워드(BM25) · 벡터(임베딩) · 혼합(RRF) 중 config로 고른다.

config 이름: "{검색}:{임베딩}"  예) "bm25", "vector:titan-512", "hybrid:titan-512", "hybrid:cohere-v4"
"best"는 eval/trust/run_retrieval.py 실험으로 고른 조합(BEST).
코퍼스: seed/corpus/courses_it.jsonl (고용24 NCS 정보기술 전체). 없으면 기존 카탈로그(seed/courses)로.
"""
import json
import math
import re
from collections import Counter
from functools import lru_cache

import numpy as np

from ..config import ROOT
from . import embed as emb

CORPUS = ROOT / "seed" / "corpus" / "courses_it.jsonl"
# 2026-11-17 실험(eval/trust/report_retrieval.md): Cohere v4 벡터가 nDCG@5 0.824로 유일하게 BM25(0.648)보다 유의하게 나음
# (차이 +0.176, 95% 구간 0.08~0.28). 교차 리전이지만 질의는 '부족한 역량 이름'이라 개인정보가 아니다(이력서는 보내지 않음).
BEST = "vector:cohere-v4"
RRF_K = 60


@lru_cache(maxsize=1)
def corpus() -> tuple[dict, ...]:
    if CORPUS.exists():
        return tuple(json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip())
    from ..data import courses
    return tuple({"doc_id": c["id"], "kind": "course", "title": c["title"], "text": f"{c['title']} · {c['provider']}",
                  "url": c.get("link"), "meta": {"provider": c["provider"], "start": c.get("start", ""),
                                                 "region": c["region"], "hours": c["hours"]}} for c in courses())


# ── 키워드 (BM25, 한국어는 형태소 분석기 없이 글자 2·3-gram) ──────────────
_TOK = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*|[0-9]+|[가-힣]+")


def tokens(text: str) -> list[str]:
    out = []
    for w in _TOK.findall(text.lower()):
        if re.match(r"[가-힣]", w):
            out += [w[i:i + n] for n in (2, 3) for i in range(max(1, len(w) - n + 1))] if len(w) > 1 else [w]
        else:
            out.append(w)
    return out


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.2, b: float = 0.75):
        self.tf = [Counter(tokens(d)) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1
        df = Counter(w for t in self.tf for w in t)
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> np.ndarray:
        q = tokens(query)
        s = np.zeros(len(self.tf), np.float32)
        for i, (tf, ln) in enumerate(zip(self.tf, self.len)):
            norm = self.k1 * (1 - self.b + self.b * ln / self.avg)
            s[i] = sum(self.idf.get(w, 0) * tf[w] * (self.k1 + 1) / (tf[w] + norm) for w in q if w in tf)
        return s


@lru_cache(maxsize=1)
def _bm25() -> BM25:
    return BM25([d["title"] for d in corpus()])


@lru_cache(maxsize=8)
def _matrix(model: str) -> np.ndarray:
    return emb.embed([d["title"] for d in corpus()], model, "document")


def _rank(scores: np.ndarray, k: int) -> list[int]:
    k = min(k, len(scores))
    idx = np.argpartition(-scores, k - 1)[:k]
    return [int(i) for i in idx[np.argsort(-scores[idx])]]


def search(query: str, k: int = 5, *, config: str = "best", kinds=None, job_family=None, log=None,
           exclude_started: bool = True) -> list[dict]:
    """→ [{chunk_id, doc_id, kind, title, url, text, score, meta}], 점수 내림차순."""
    from datetime import date
    config = BEST if config == "best" else config
    method, _, model = config.partition(":")
    docs = corpus()
    if method == "bm25":
        s = _bm25().scores(query)
        order = _rank(s, k * 4)
    else:
        q = emb.embed([query], model, "query", log=log)[0]
        sv = _matrix(model) @ q
        if method == "vector":
            s, order = sv, _rank(sv, k * 4)
        else:  # hybrid: 순위 융합(RRF). 점수 크기가 다른 두 검색을 순위로만 합친다
            pool = 100
            rv, rb = _rank(sv, pool), _rank(_bm25().scores(query), pool)
            fused: dict[int, float] = {}
            for r in (rv, rb):
                for pos, i in enumerate(r):
                    fused[i] = fused.get(i, 0) + 1 / (RRF_K + pos + 1)
            order = sorted(fused, key=lambda i: -fused[i])
            s = np.zeros(len(docs), np.float32)
            for i, v in fused.items():
                s[i] = v
    today = date.today().isoformat()
    out = []
    for i in order:
        d = docs[i]
        if exclude_started and d.get("meta", {}).get("start") and d["meta"]["start"] < today:
            continue
        if kinds and d["kind"] not in kinds:
            continue
        out.append({"chunk_id": d["doc_id"], "doc_id": d["doc_id"], "kind": d["kind"], "title": d["title"], "url": d.get("url"),
                    "text": d["text"], "score": float(s[i]), "meta": d.get("meta", {})})
        if len(out) == k:
            break
    return out
