"""교육 추천 '맞는 과정 없음' 기준값 정하기 (2026-11-20).

배포에서 'AI 에이전트' 부족에 'AI Agent를 활용한 디지털 미디어 콘텐츠 Innovator'가 1위로 나왔다.
검색 1위면 점수가 낮아도 추천하던 것을, 유사도가 기준 아래면 추천하지 않게(거부) 바꾼다.

데이터: 검색 실험의 판정(judge_retrieval.json, 질의 40개 × 과정 1,191쌍, Sonnet 0/1/2, 사람 재판정 일치 77%).
점수: 서비스와 같은 Cohere Embed v4 코사인 유사도(질의 임베딩 · 과정 임베딩).
- 쌍 단위: 점수가 t 이상인 쌍 중 무관(0) 비율
- 1위 단위: 질의마다 판정된 과정 중 점수 1위 → t 미만이면 거부. 추천 중 무관 비율과 추천한 질의 비율
→ 기준: 1위 추천의 무관 비율이 가장 낮아지면서 추천 비율을 최대한 남기는 t (결과 표를 보고 하나 고른다)
실행: python eval/trust/abstain_threshold.py  (질의 임베딩은 캐시, 없으면 Bedrock 호출)
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    from app.rag import embed as emb
    from app.rag import retrieve as R
    judged = json.loads((HERE / "judge_retrieval.json").read_text(encoding="utf-8"))
    docs = R.corpus()
    row = {d["doc_id"]: i for i, d in enumerate(docs)}
    M = R._matrix("cohere-v4")
    queries = sorted({k.split("||")[0] for k in judged})
    Q = dict(zip(queries, emb.embed(queries, "cohere-v4", "query")))
    pairs = []  # (query, score, label)
    for k, lab in judged.items():
        q, did = k.split("||")
        if did in row:
            pairs.append((q, float(M[row[did]] @ np.asarray(Q[q])), int(lab)))
    top1 = {}
    for q, s, lab in pairs:
        if q not in top1 or s > top1[q][0]:
            top1[q] = (s, lab)

    ts = [round(float(x), 2) for x in np.arange(0.20, 0.56, 0.02)]
    pair_rows, top_rows = [], []
    for t in ts:
        kept = [lab for _, s, lab in pairs if s >= t]
        pair_rows.append((t, len(kept), sum(l == 0 for l in kept) / len(kept) if kept else None))
        rec = [lab for s, lab in top1.values() if s >= t]
        top_rows.append((t, len(rec) / len(top1), sum(l == 0 for l in rec) / len(rec) if rec else None,
                         int(sum(s < t and lab >= 1 for s, lab in top1.values()))))
    s_all = sorted(top1.values())
    out = {"_meta": {"pairs": len(pairs), "queries": len(top1), "model": "cohere-v4",
                     "note": "판정은 Sonnet(사람 재판정 일치 77%). 질의 40개라 기준값은 참고치"},
           "pair": [{"t": t, "kept": n, "irrelevant": r} for t, n, r in pair_rows],
           "top1": [{"t": t, "recommend_rate": c, "irrelevant_in_recommended": r, "lost_relevant": lost} for t, c, r, lost in top_rows],
           "top1_scores": [{"query": q, "score": round(s, 3), "label": lab} for q, (s, lab) in sorted(top1.items(), key=lambda x: x[1][0])]}
    (HERE / "results_abstain.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"쌍 {len(pairs)} · 질의 {len(top1)}")
    print("t     | 1위 추천 비율 | 추천 중 무관 | 버려진 관련 1위 | (쌍) t 이상 무관 비율")
    for (t, c, r, lost), (_, n, pr) in zip(top_rows, pair_rows):
        print(f"{t:.2f}  | {c:6.1%}       | {('—' if r is None else f'{r:5.1%}')}       | {lost:3d}            | {('—' if pr is None else f'{pr:5.1%}')} ({n})")
    print("\n1위 점수가 낮은 질의:")
    for q, (s, lab) in sorted(top1.items(), key=lambda x: x[1][0])[:10]:
        print(f"  {s:.3f}  판정 {lab}  {q}")


if __name__ == "__main__":
    main()
