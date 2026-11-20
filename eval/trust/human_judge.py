"""검색 판정(Sonnet)을 사람이 다시 판정해 일치도를 잰다.

1) python eval/trust/human_judge.py make    → judge_human.csv (30쌍, Sonnet 점수는 넣지 않음)
2) 엑셀로 열어 '내 점수' 칸에 0/1/2 입력, 저장(CSV UTF-8)
3) python eval/trust/human_judge.py score   → 일치율·κ·혼동표, judge_human_result.json

표본: Sonnet 점수 0/1/2에서 10쌍씩 층화 추출(seed 고정) 후 섞는다. 사람 판정은 Sonnet과 같은 조건(과정명만 보고).
층화 표본이라 κ는 '점수별로 고르게 뽑은 쌍'에서의 일치도다(전체 판정 분포와 다름 → 보고서에 밝힌다).
"""
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "trust"
JUDGE = OUT / "judge_retrieval.json"
SHEET = OUT / "judge_human.csv"
RESULT = OUT / "judge_human_result.json"
CORPUS = ROOT / "seed" / "corpus" / "courses_it.jsonl"
PER_LABEL, SEED = 10, 20261118
RULE = ["# 판정 기준(Sonnet과 같음): 취업 준비생이 '질의' 역량을 배우려 할 때 이 과정이 맞는가. 과정명만 보고, 이름에 없는 내용은 상상하지 않는다.",
        "# 2 = 과정의 주제가 바로 그 역량 / 1 = 일부 다루거나 선행·연관 과정 / 0 = 무관.  '내 점수' 칸만 채운다. key 칸은 고치지 않는다."]
COLS = ["no", "질의(배우려는 역량)", "과정명", "내 점수", "메모", "key"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def make():
    if SHEET.exists():
        sys.exit(f"{SHEET.name}이 이미 있음(판정을 덮어쓰지 않게 멈춤). 새로 뽑으려면 직접 지우고 다시 실행")
    judged = json.loads(JUDGE.read_text(encoding="utf-8"))
    titles = {d["doc_id"]: d["title"] for d in map(json.loads, CORPUS.read_text(encoding="utf-8").splitlines())}
    rnd = random.Random(SEED)
    pick = []
    for lab in (0, 1, 2):
        keys = sorted(k for k, v in judged.items() if v == lab and k.split("||")[1] in titles)
        pick += rnd.sample(keys, PER_LABEL)
    rnd.shuffle(pick)
    with SHEET.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: 엑셀에서 한글이 안 깨짐
        w = csv.writer(f)
        for r in RULE:
            w.writerow([r])
        w.writerow(COLS)
        for i, k in enumerate(pick, 1):
            q, doc = k.split("||")
            w.writerow([i, q, titles[doc], "", "", k])
    print(f"{SHEET} 생성: {len(pick)}쌍 (Sonnet 0/1/2 각 {PER_LABEL}쌍, 섞음)")


def kappa(a: list[int], b: list[int], weighted: bool = False) -> float:
    cats = (0, 1, 2)
    n = len(a)
    w = (lambda i, j: abs(i - j) / 2) if weighted else (lambda i, j: float(i != j))
    obs = sum(w(x, y) for x, y in zip(a, b)) / n
    pa, pb = Counter(a), Counter(b)
    exp = sum(pa[i] * pb[j] * w(i, j) for i in cats for j in cats) / n / n
    return 1 - obs / exp if exp else 1.0


def boot(a, b, fn, n=2000):
    rnd = random.Random(0)
    idx = range(len(a))
    vals = []
    for _ in range(n):
        s = [rnd.choice(idx) for _ in idx]
        vals.append(fn([a[i] for i in s], [b[i] for i in s]))
    vals.sort()
    return [round(fn(a, b), 3), round(vals[int(0.025 * n)], 3), round(vals[int(0.975 * n)], 3)]


def score():
    judged = json.loads(JUDGE.read_text(encoding="utf-8"))
    raw = SHEET.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:  # 엑셀에서 'CSV(쉼표로 분리)'로 저장하면 cp949
        text = raw.decode("cp949")
    rows = [r for r in csv.reader(text.splitlines()) if r and not r[0].startswith("#")]
    head, rows = rows[0], rows[1:]
    ci, ck = head.index("내 점수"), head.index("key")
    bad = [r[0] for r in rows if r[ci].strip() not in ("0", "1", "2")]
    if bad:
        sys.exit(f"'내 점수'가 0/1/2가 아닌 줄: {', '.join(bad)}")
    human = [int(r[ci]) for r in rows]
    llm = [judged[r[ck]] for r in rows]
    agree = lambda a, b: sum(x == y for x, y in zip(a, b)) / len(a)  # noqa: E731
    binr = lambda xs: [int(x >= 1) for x in xs]  # noqa: E731
    res = {
        "n": len(rows), "sampling": f"Sonnet 0/1/2 층화 각 {PER_LABEL}쌍, seed {SEED}",
        "exact_agreement": boot(human, llm, agree),
        "kappa": boot(human, llm, kappa),
        "kappa_linear_weighted": boot(human, llm, lambda a, b: kappa(a, b, True)),
        "binary_agreement(관련>=1)": boot(binr(human), binr(llm), agree),
        "confusion[사람][Sonnet]": [[sum(h == i and l == j for h, l in zip(human, llm)) for j in (0, 1, 2)] for i in (0, 1, 2)],
        "disagreements": [{"no": r[0], "query": r[1], "title": r[2], "human": h, "sonnet": l, "memo": r[head.index("메모")]}
                          for r, h, l in zip(rows, human, llm) if h != l],
    }
    RESULT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"n={res['n']} ({res['sampling']})  값 [평균, 95% 구간]")
    for k in ("exact_agreement", "kappa", "kappa_linear_weighted", "binary_agreement(관련>=1)"):
        print(f"  {k}: {res[k]}")
    print("  혼동표 (행=사람 0/1/2, 열=Sonnet 0/1/2):")
    for i, row in enumerate(res["confusion[사람][Sonnet]"]):
        print(f"    사람 {i}: {row}")
    print(f"  불일치 {len(res['disagreements'])}건 → {RESULT.name}")


if __name__ == "__main__":
    {"make": make, "score": score}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
