"""T2 RAG 골격: 청크 → 임베딩 캐시 → 검색 (BEDROCK_MOCK=1, 과정 카탈로그 코퍼스)."""
import pytest

from app.adapters import bedrock
from app.rag import chunk, embed_cache, retrieve
from app.rag.hybrid import rrf

TEXT = "요구사항을 확인한다. " * 120  # 1,000토큰 이상


def test_ntokens():
    # SQL(1) 개·발·자(3) 2(1) 급(1) ,(1) 합·격(2) !(1) = 10
    assert chunk.ntokens("SQL 개발자 2급, 합격!") == 10


@pytest.mark.parametrize("n,p", [(200, 0), (300, 15), (1000, 0)])
def test_fixed_windows(n, p):
    parts = chunk.split(TEXT, f"fixed{n}o{p}")
    assert all(chunk.ntokens(c["text"]) <= n for c in parts)
    assert len(parts) >= chunk.ntokens(TEXT) // n
    if p:  # 겹침: 다음 청크 앞부분이 이전 청크 끝과 같다
        assert parts[1]["text"][:5] in parts[0]["text"]


def test_hier_and_struct():
    h = chunk.split(TEXT, "hier1500_300")
    assert all(chunk.ntokens(c["text"]) <= 300 and c["text"] in c["parent"] for c in h)
    s = chunk.split("1.1 요구사항을 수집한다\n\n1.2 요구사항을 분석한다\n", "struct")
    assert [c["text"] for c in s] == ["1.1 요구사항을 수집한다", "1.2 요구사항을 분석한다"]


def test_every_strategy_runs():
    for st in chunk.STRATEGIES:
        assert chunk.split(TEXT, st)


def test_embed_cache_second_run_no_calls(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(embed_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(embed_cache, "_mem", {})
    monkeypatch.setattr(embed_cache, "_titan", lambda t, d: (calls.append(t), ([0.1] * d, 7))[1])
    a = embed_cache.embed(["가나다", "라마바", "가나다"], dims=256)
    assert len(calls) == 2 and len(a) == 3 and a[0] == a[2]
    monkeypatch.setattr(embed_cache, "_mem", {})  # 프로세스 재시작 흉내: 디스크에서 읽어야 함
    embed_cache.embed(["가나다", "라마바"], dims=256)
    assert len(calls) == 2
    assert embed_cache.true_tokens(["가나다"], dims=256) == [7]


def test_rrf():
    assert [i for i, _ in rrf([[1, 2, 3], [2, 1, 3]])][:2] in ([1, 2], [2, 1])
    assert [i for i, _ in rrf([[1, 2], [2, 3]])][0] == 2  # 둘 다 위에 있는 것이 1등


KEYS = {"chunk_id", "doc_id", "kind", "title", "url", "text", "score"}


@pytest.mark.parametrize("config", ["best", "bm25|t2v512|struct", "dense|t2v256|fixed300o15",
                                    "hybrid|t2v1024|hier1500_300|rr"])
def test_search_contract(config):
    hits = retrieve.search("SQL 데이터베이스 과정", k=5, config=config)
    assert 0 < len(hits) <= 5
    assert all(set(h) == KEYS for h in hits)
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)


def test_search_relevant_and_filters():
    hits = retrieve.search("SQL", k=3, config="bm25|t2v512|struct")
    assert any("SQL" in h["title"].upper() for h in hits)
    assert retrieve.search("SQL", kinds=["ncs_unit"]) == []
    assert all(h["kind"] == "course" for h in retrieve.search("SQL", kinds=["course"]))


def test_dense_failure_falls_back_to_bm25(monkeypatch):
    def boom(*a, **k):
        raise bedrock.BedrockError("로그인 만료")
    monkeypatch.setattr(embed_cache, "embed", boom)
    assert retrieve.search("SQL", config="dense|t2v512|struct")


def test_bad_config():
    with pytest.raises(ValueError):
        retrieve.search("x", config="magic|t2v512|struct")


def test_one_hit_per_doc():
    hits = retrieve.search("SQL 자격증", k=5, config="bm25|t2v512|struct")
    assert len({h["doc_id"] for h in hits}) == len(hits)
