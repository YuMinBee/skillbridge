"""교육 추천 검색(RAG) 조합 비교 → eval/trust/results_retrieval.json + report_retrieval.md

무엇을 재나: 부족한 역량(질의)으로 고용24 정보기술 과정 수천 개 중 맞는 과정을 상위 5개 안에 찾는가.
비교: 키워드(BM25, 기존 방식과 같은 계열) · 벡터(Titan 256/512/1024, Cohere v4) · 혼합(RRF).

정답 만들기 (TREC 방식 풀링 + LLM 판정)
- 질의마다 모든 조합의 상위 POOL개를 모아 중복을 뺀 뒤, 판정 모델이 관련도 0/1/2를 매긴다.
  2 = 과정의 주제가 그 역량, 1 = 일부 다룸, 0 = 무관. 판정은 eval/trust/judge_retrieval.json에 저장(다시 안 부름).
- 판정에 LLM을 쓴 것은 보고서에 밝힌다. 사람 확인용 표본은 --sample로 뽑는다.
- 질의는 실험 전에 고정(QUERIES). 조합을 고른 뒤 질의를 바꾸지 않는다.

실행: python eval/trust/run_retrieval.py          (Bedrock: 임베딩 + 판정, 처음 몇 분·몇 센트, 다음부터 캐시)
"""
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.adapters import bedrock  # noqa: E402
from app.rag import retrieve as R  # noqa: E402

OUT = ROOT / "eval" / "trust"
JUDGE_CACHE = OUT / "judge_retrieval.json"  # 판정 결과는 커밋한다(재현용, 개인정보 없음)
CONFIGS = ["bm25", "vector:titan-256", "vector:titan-512", "vector:titan-1024", "vector:cohere-v4",
           "hybrid:titan-512", "hybrid:cohere-v4"]
POOL, K = 10, 5

# 질의 (실험 전에 고정). name = 우리 서비스가 실제로 던지는 질의(부족한 역량 이름),
# need = 사람이 말하듯 쓴 요구(같은 단어가 과정명에 없을 수 있음 → 의미 검색이 필요한 경우)
QUERIES = [
    ("name", "Kubernetes"), ("name", "Docker"), ("name", "MLOps"), ("name", "AWS"), ("name", "Spring"),
    ("name", "Java"), ("name", "Python"), ("name", "SQL"), ("name", "React"), ("name", "PyTorch"),
    ("name", "머신러닝"), ("name", "딥러닝"), ("name", "자연어처리"), ("name", "컴퓨터 비전"), ("name", "LLM"),
    ("name", "데이터 분석"), ("name", "데이터 파이프라인"), ("name", "Linux"), ("name", "네트워크"), ("name", "정보보안"),
    ("name", "REST API"), ("name", "Git"), ("name", "Kafka"), ("name", "TypeScript"), ("name", "정보처리기사"),
    ("need", "컨테이너로 서비스를 배포하고 여러 서버에서 자동으로 운영하는 법"),
    ("need", "학습한 모델을 서비스로 배포하고 성능을 모니터링하는 법"),
    ("need", "클라우드에 서버를 올리고 비용과 권한을 관리하는 법"),
    ("need", "자바로 웹 서버 API를 만드는 법"),
    ("need", "대용량 데이터를 모아서 정제하고 저장하는 흐름 만들기"),
    ("need", "문장을 이해하는 챗봇이나 텍스트 분류 모델 만들기"),
    ("need", "사진 속 물체를 찾아내는 모델 만들기"),
    ("need", "챗GPT 같은 언어모델에 우리 문서를 붙여서 답하게 하기"),
    ("need", "엑셀 대신 코드로 데이터를 분석하고 그래프 그리기"),
    ("need", "웹 화면을 컴포넌트로 만드는 프런트엔드 개발"),
    ("need", "해킹을 막기 위한 서버 보안 설정"),
    ("need", "코드 변경을 자동으로 테스트하고 배포하는 파이프라인"),
    ("need", "데이터베이스 설계와 쿼리 튜닝"),
    ("need", "리눅스 서버를 명령어로 다루는 법"),
    ("need", "정보처리기사 자격증 시험 준비"),
]

_JUDGE_SYS = """너는 직업훈련 과정 평가자다. 취업 준비생이 어떤 역량을 배우려 할 때 이 훈련과정이 맞는지 판정한다.
2 = 과정의 주제가 바로 그 역량이다. 1 = 그 역량을 일부 다루거나 선행/연관 과정이다. 0 = 무관하다.
과정명만 보고 판단하되, 이름에 없는 내용을 상상하지 않는다."""
_JUDGE_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
    "i": {"type": "integer"}, "rel": {"type": "integer", "enum": [0, 1, 2]}}, "required": ["i", "rel"]}}}, "required": ["items"]}


def judge(query: str, docs: list[dict], cache: dict) -> dict[str, int]:
    todo = [d for d in docs if f"{query}||{d['doc_id']}" not in cache]
    for s in range(0, len(todo), 40):
        part = todo[s:s + 40]
        lst = "\n".join(f"{i}. {d['title']}" for i, d in enumerate(part))
        out = bedrock.converse_tool(_JUDGE_SYS, f"<배우려는 역량>{query}</배우려는 역량>\n<과정>\n{lst}\n</과정>",
                                    "submit_rel", _JUDGE_SCHEMA, kind="judge", max_tokens=2000)
        got = {it["i"]: it["rel"] for it in out.get("items", []) if isinstance(it, dict)}
        for i, d in enumerate(part):
            cache[f"{query}||{d['doc_id']}"] = int(got.get(i, 0))
    return {d["doc_id"]: cache[f"{query}||{d['doc_id']}"] for d in docs}


def ndcg(rels: list[int], ideal: list[int], k: int = K) -> float:
    import math
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(sorted(ideal, reverse=True)[:k]))
    return dcg / idcg if idcg else 0.0


def boot(vals: list[float], n: int = 2000, seed: int = 0) -> list[float]:
    rnd = random.Random(seed)
    m = sum(vals) / len(vals)
    bs = sorted(sum(rnd.choice(vals) for _ in vals) / len(vals) for _ in range(n))
    return [round(m, 3), round(bs[int(0.025 * n)], 3), round(bs[int(0.975 * n)], 3)]


def main():
    print(f"코퍼스 {len(R.corpus()):,}개 과정 · 질의 {len(QUERIES)}개 · 조합 {len(CONFIGS)}개")
    for c in CONFIGS:  # 문서 임베딩 (캐시)
        if ":" in c:
            t0 = time.time()
            R._matrix(c.split(":")[1])
            print(f"  임베딩 준비 {c.split(':')[1]}: {time.time() - t0:.0f}s")
    runs, lat = {c: {} for c in CONFIGS}, {c: [] for c in CONFIGS}
    for _, q in QUERIES:
        for c in CONFIGS:
            t0 = time.perf_counter()
            runs[c][q] = R.search(q, POOL, config=c, exclude_started=False)
            lat[c].append((time.perf_counter() - t0) * 1000)
    cache = json.loads(JUDGE_CACHE.read_text(encoding="utf-8")) if JUDGE_CACHE.exists() else {}
    qrels = {}
    for i, (_, q) in enumerate(QUERIES, 1):
        pool = {d["doc_id"]: d for c in CONFIGS for d in runs[c][q]}
        qrels[q] = judge(q, list(pool.values()), cache)
        if i % 10 == 0:
            print(f"  판정 {i}/{len(QUERIES)}")
    JUDGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    JUDGE_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    res = {"_meta": {"at": time.strftime("%Y-%m-%d %H:%M"), "corpus": len(R.corpus()), "queries": len(QUERIES), "pool": POOL, "k": K,
                     "judge": bedrock.short_model(bedrock.MODEL_ID), "note": "정답은 풀링+LLM 판정(사람 표본 확인 필요)"},
           "configs": {}}
    per = {}
    for c in CONFIGS:
        rows = {"ndcg@5": [], "recall@5": [], "mrr": [], "p@5": []}
        for typ, q in QUERIES:
            rel = qrels[q]
            got = [rel.get(d["doc_id"], 0) for d in runs[c][q]]
            n_rel = sum(1 for v in rel.values() if v >= 1)
            rows["ndcg@5"].append(ndcg(got, list(rel.values())))
            rows["recall@5"].append(sum(1 for v in got[:K] if v >= 1) / min(K, n_rel) if n_rel else 0.0)
            rows["mrr"].append(next((1 / (i + 1) for i, v in enumerate(got) if v >= 1), 0.0))
            rows["p@5"].append(sum(1 for v in got[:K] if v >= 1) / K)
        per[c] = rows
        name_idx = [i for i, (t, _) in enumerate(QUERIES) if t == "name"]
        need_idx = [i for i, (t, _) in enumerate(QUERIES) if t == "need"]
        model = c.split(":")[1] if ":" in c else None
        res["configs"][c] = {**{m: boot(v) for m, v in rows.items()},
                             "ndcg@5_name": boot([rows["ndcg@5"][i] for i in name_idx]),
                             "ndcg@5_need": boot([rows["ndcg@5"][i] for i in need_idx]),
                             "p50_ms": round(sorted(lat[c])[len(lat[c]) // 2]), "region": R.emb.MODELS[model]["region"] if model else "로컬"}
    # 지연: 질의 임베딩은 캐시를 거치지 않고 Bedrock을 직접 불러 잰다(실제 사용자 요청과 같은 조건) + 로컬 검색 시간
    emb_ms = {}
    for m in {c.split(":")[1] for c in CONFIGS if ":" in c}:
        info, ts = R.emb.MODELS[m], []
        for _, q in QUERIES[:15]:
            t0 = time.perf_counter()
            (R.emb._titan([q], info["dims"]) if info["kind"] == "titan" else R.emb._cohere([q], "query"))
            ts.append((time.perf_counter() - t0) * 1000)
        emb_ms[m] = sorted(ts)[len(ts) // 2]
    for c in CONFIGS:
        m = c.split(":")[1] if ":" in c else None
        local = res["configs"][c]["p50_ms"]
        res["configs"][c]["p50_ms"] = round(local + (emb_ms[m] if m else 0))
        res["configs"][c]["embed_ms"] = round(emb_ms[m]) if m else 0
    # 기준(bm25) 대비 짝지은 차이와 구간
    base = per["bm25"]["ndcg@5"]
    for c in CONFIGS:
        res["configs"][c]["delta_vs_bm25"] = boot([a - b for a, b in zip(per[c]["ndcg@5"], base)])
    (OUT / "results_retrieval.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    L = [f"# 교육 추천 검색 비교 ({res['_meta']['at']})", "",
         f"고용24 NCS 정보기술 과정 {res['_meta']['corpus']:,}개 · 질의 {len(QUERIES)}개(역량 이름 25 + 자연어 요구 15) · "
         f"정답: 조합별 상위 {POOL}개 풀링 + {res['_meta']['judge']} 판정(0/1/2). 값 [평균, 95% 구간].", "",
         "| 조합 | nDCG@5 | 이름 질의 | 자연어 질의 | Recall@5 | MRR | BM25 대비 nDCG 차이 | 지연 p50 | 처리 위치 |", "|---|---|---|---|---|---|---|---|---|"]
    f = lambda v: f"{v[0]:.3f} [{v[1]:.2f}, {v[2]:.2f}]"  # noqa: E731
    for c in CONFIGS:
        r = res["configs"][c]
        d = r["delta_vs_bm25"]
        sig = "" if c == "bm25" else (" ✓" if d[1] > 0 else (" ✗" if d[2] < 0 else " (유의 아님)"))
        L.append(f"| {c} | {f(r['ndcg@5'])} | {r['ndcg@5_name'][0]:.3f} | {r['ndcg@5_need'][0]:.3f} | {f(r['recall@5'])} | {r['mrr'][0]:.3f} | "
                 f"{'—' if c == 'bm25' else f(d) + sig} | {r['p50_ms']}ms | {r['region']} |")
    L += ["", "✓ = 구간이 0보다 큼(유의하게 나음), ✗ = 유의하게 나쁨. 지연 = 질의 임베딩 Bedrock 호출(캐시 없이 15회 중앙값) + 로컬 검색.",
          "주의: 정답은 LLM 판정이다. 사람 표본 확인 전에는 '사람 기준 정확도'라고 말하지 않는다."]
    (OUT / "report_retrieval.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
