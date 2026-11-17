"""RRF(Reciprocal Rank Fusion): 순위만 써서 BM25와 벡터 검색을 합친다(점수 스케일이 달라도 됨)."""


def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """rankings: 각 검색기의 결과 인덱스(좋은 순) → [(인덱스, 점수)] 내림차순."""
    s: dict[int, float] = {}
    for r in rankings:
        for rank, i in enumerate(r):
            s[i] = s.get(i, 0.0) + 1.0 / (k + rank + 1)
    return sorted(s.items(), key=lambda x: -x[1])
