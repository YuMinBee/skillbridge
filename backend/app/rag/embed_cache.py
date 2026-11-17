"""임베딩 + 디스크 캐시. 같은 (모델, 차원, 문장)은 Bedrock을 두 번 부르지 않는다.

캐시: eval/trust/cache/{모델}_{차원}.json = {sha1(문장): {"v": 벡터, "tok": 실제 토큰 수}}
청크 설정이 다르면 문장이 달라지므로 키에 따로 넣지 않는다(같은 문장은 공유).
모델 "mock"은 AWS 없이 도는 결정적 해시 임베딩이다(테스트·BEDROCK_MOCK=1용, 실험 숫자에 쓰지 않는다).
"""
import hashlib
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..adapters import bedrock
from ..config import ROOT

CACHE_DIR = Path(os.getenv("RAG_CACHE_DIR", ROOT / "eval" / "trust" / "cache"))
TITAN = "amazon.titan-embed-text-v2:0"
# ponytail: Titan만. Cohere v4(global. 프로필)는 조합 실험 때 요청 형식 확인 후 추가


def _key(t: str) -> str:
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


def _mock(t: str, dims: int) -> list[float]:
    v = [0.0] * dims
    for i in range(len(t) - 1):
        v[int(_key(t[i:i + 2])[:8], 16) % dims] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _titan(t: str, dims: int) -> tuple[list[float], int]:
    r = bedrock.client().invoke_model(modelId=TITAN,
                                      body=json.dumps({"inputText": t, "dimensions": dims, "normalize": True}))
    b = json.loads(r["body"].read())
    return b["embedding"], b.get("inputTextTokenCount", 0)


def _path(model: str, dims: int) -> Path:
    return CACHE_DIR / f"{model.replace(':', '_').replace('/', '_')}_{dims}.json"


_mem: dict[Path, dict] = {}


def embed(texts: list[str], model: str = TITAN, dims: int = 512, *, log: bedrock.CallLog | None = None) -> list[list[float]]:
    if model == "mock":
        return [_mock(t, dims) for t in texts]
    p = _path(model, dims)
    cache = _mem.get(p)
    if cache is None:
        cache = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        _mem[p] = cache
    todo = list({_key(t): t for t in texts if _key(t) not in cache}.items())
    if todo:
        t0 = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=8) as ex:
                got = list(ex.map(lambda kt: _titan(kt[1], dims), todo))
        except Exception as e:  # noqa: BLE001
            raise bedrock._wrap(e) from e
        for (k, _), (v, tok) in zip(todo, got):
            cache[k] = {"v": v, "tok": tok}
        if log is not None:
            log.add("embed", model, (time.perf_counter() - t0) * 1000, sum(t for _, t in got), 0)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:  # 읽기 전용 파일시스템(Lambda)에서는 메모리 캐시만
            pass
    return [cache[_key(t)]["v"] for t in texts]


def true_tokens(texts: list[str], model: str = TITAN, dims: int = 512) -> list[int | None]:
    """캐시에 저장된 실제 토큰 수 (chunk.ntokens 근사 보정용)."""
    cache = _mem.get(_path(model, dims), {})
    return [cache.get(_key(t), {}).get("tok") for t in texts]
