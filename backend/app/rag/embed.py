"""임베딩 (Bedrock, 서울 리전). 모델별로 결과를 캐시해서 같은 글은 한 번만 호출한다.

모델 (2026-11-17 서울 리전 실제 호출로 확인, docs/pivot/T2_RAG.md)
- titan-256 / titan-512 / titan-1024 : amazon.titan-embed-text-v2:0 (서울 안에서 처리, 한 번에 글 1개)
- cohere-v4                          : global.cohere.embed-v4:0 (교차 리전, 한 번에 96개, 문서/질의 구분)
캐시: backend/.data/emb/{모델}.npz (sha1(글) → 벡터). 정규화된 벡터라 내적 = 코사인 유사도.
"""
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..adapters import bedrock
from ..config import BUNDLED_CACHE, ON_LAMBDA, ROOT

# Lambda는 /var/task가 읽기 전용 → 쓰기는 /tmp, 읽기는 /tmp → 배포 패키지에 미리 구운 벡터(cache_bundle/emb) 순서
CACHE = Path("/tmp/.data/emb") if ON_LAMBDA else ROOT / "backend" / ".data" / "emb"
BUNDLED = BUNDLED_CACHE / "emb"
MODELS = {
    "titan-256": {"id": "amazon.titan-embed-text-v2:0", "dims": 256, "kind": "titan", "region": "서울", "usd_per_mtok": 0.02},
    "titan-512": {"id": "amazon.titan-embed-text-v2:0", "dims": 512, "kind": "titan", "region": "서울", "usd_per_mtok": 0.02},
    "titan-1024": {"id": "amazon.titan-embed-text-v2:0", "dims": 1024, "kind": "titan", "region": "서울", "usd_per_mtok": 0.02},
    "cohere-v4": {"id": "global.cohere.embed-v4:0", "dims": 1536, "kind": "cohere", "region": "교차 리전", "usd_per_mtok": 0.12},
}
_lock = threading.Lock()
_mem: dict[str, dict[str, np.ndarray]] = {}


def _key(text: str, purpose: str, model: str) -> str:
    p = purpose if MODELS[model]["kind"] == "cohere" else "-"  # Titan은 문서·질의 구분이 없다
    return hashlib.sha1(f"{p}|{text}".encode()).hexdigest()


def _load(model: str) -> dict[str, np.ndarray]:
    if model not in _mem:
        f = next((c / f"{model}.npz" for c in (CACHE, BUNDLED) if (c / f"{model}.npz").exists()), None)
        _mem[model] = dict(np.load(f)) if f else {}
    return _mem[model]


def _save(model: str):
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        np.savez(CACHE / f"{model}.npz", **_mem[model])
    except OSError:
        pass  # 캐시는 있으면 좋은 것. 못 써도 검색은 메모리에 있는 벡터로 계속한다


def _titan(texts: list[str], dims: int) -> list[list[float]]:
    def one(t):
        r = bedrock.client().invoke_model(modelId=MODELS["titan-512"]["id"],
                                          body=json.dumps({"inputText": t[:8000], "dimensions": dims, "normalize": True}))
        return json.loads(r["body"].read())["embedding"]
    with ThreadPoolExecutor(max_workers=12) as ex:
        return list(ex.map(one, texts))


def _cohere(texts: list[str], purpose: str) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 96):
        body = {"texts": [t[:2000] for t in texts[i:i + 96]], "input_type": f"search_{purpose}", "embedding_types": ["float"]}
        r = json.loads(bedrock.client().invoke_model(modelId=MODELS["cohere-v4"]["id"], body=json.dumps(body))["body"].read())
        e = r["embeddings"]
        out += e["float"] if isinstance(e, dict) else e
    return out


def embed(texts: list[str], model: str = "titan-512", purpose: str = "document", log=None) -> np.ndarray:
    """→ (len(texts), dims) 정규화 행렬. purpose: document | query"""
    m = MODELS[model]
    with _lock:
        cache = _load(model)
        keys = [_key(t, purpose, model) for t in texts]
        todo = list(dict.fromkeys(t for t, k in zip(texts, keys) if k not in cache))
    if todo:
        t0 = time.perf_counter()
        try:
            vecs = _titan(todo, m["dims"]) if m["kind"] == "titan" else _cohere(todo, purpose)
        except Exception as e:  # noqa: BLE001
            raise bedrock._wrap(e) from e
        if log is not None:
            log.add(f"embed:{model}", m["id"], (time.perf_counter() - t0) * 1000, sum(len(t) for t in todo) // 2, 0)
        with _lock:
            for t, v in zip(todo, vecs):
                a = np.asarray(v, dtype=np.float32)
                cache[_key(t, purpose, model)] = a / (np.linalg.norm(a) or 1.0)
            _save(model)
    with _lock:
        return np.stack([cache[k] for k in keys]) if keys else np.zeros((0, m["dims"]), np.float32)
