"""평가용 공고 표본 추출 (재현 가능, seed 고정).

잡알리오 실공고에서 디지털 단서가 있는 공고 20건 + 무작위 10건(오탐 측정용)을 뽑는다.
단서 정규식은 '표본을 고르는 데만' 쓰고 정답 라벨과는 무관하다 (라벨은 사람이 본문을 읽고 붙인다).
출력: eval/postings_to_label.jsonl (id, company, title, text) — 라벨러가 labels 필드를 채운다.
"""
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HINT = re.compile(r"컴퓨터활용|컴활|정보처리|엑셀|Excel|오피스|OA|한글|워드프로세서|ITQ|빅데이터|데이터 ?분석|통계 ?프로그램|SPSS|SAS|파이썬|Python|SQL|인공지능|AI|프로그래밍|코딩|소프트웨어|정보보안|네트워크|클라우드|리눅스|ADsP|GIS|CAD")
N_HINT, N_RAND, SEED = 20, 10, 6


def main():
    rows = [json.loads(l) for l in open(ROOT / "seed/market/postings_live.jsonl", encoding="utf-8")]
    rows = [r for r in rows if 80 <= len(r["text"]) <= 1500]  # 너무 짧거나 긴 공고는 라벨 부담 때문에 제외
    rng = random.Random(SEED)
    hint = [r for r in rows if HINT.search(r["text"])]
    pick = rng.sample(hint, N_HINT)
    ids = {r["id"] for r in pick}
    pick += rng.sample([r for r in rows if r["id"] not in ids], N_RAND)
    out = ROOT / "eval/postings_to_label.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in pick:
            f.write(json.dumps({"id": r["id"], "company": r["company"], "title": r["title"], "text": r["text"]}, ensure_ascii=False) + "\n")
    print(f"{len(pick)}건 → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
