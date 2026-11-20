"""과제 구체화 사람 판정 (2026-11-20). results_tasks.json의 LLM 과제(원문 대조 통과분)를 사람이 읽고 판정한다.

python eval/trust/task_judge.py make    → task_judge.csv (판정 칸 비움)
python eval/trust/task_judge.py score   → task_judge_result.json (적절 비율 + 95% 구간)

판정 기준(한 과제씩, 자소서 원문은 eval/trust/task_essays/essays.jsonl · 시연 자소서):
- 적절: 이 지원자가 1~2주 안에 혼자 할 수 있고, 그 역량을 보여 주는 결과물이 남고, 자소서에 없는 일을 했다고 가정하지 않음
- 애매: 방향은 맞지만 너무 크거나(한 달 이상), 역량과 연결이 약함
- 부적절: 역량과 무관, 지원자 경험을 잘못 이해, 할 수 없는 일
판정하는 사람은 우리 시스템 코드를 보지 않고 과제 문장과 근거만 본다. 엑셀로 열어 '판정' 칸에 적절/애매/부적절.
"""
import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV = HERE / "task_judge.csv"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
COLS = ["no", "자소서", "역량", "과제", "근거_공고", "근거_자소서", "판정", "메모"]


def make():
    d = json.loads((HERE / "results_tasks.json").read_text(encoding="utf-8"))
    rows, n = [], 0
    for r in d["runs"]:
        for x in r["recos"]:
            if x.get("via") != "llm":
                continue
            n += 1
            b = x.get("basis") or {}
            rows.append({"no": n, "자소서": r["id"], "역량": x["target"], "과제": x["task"],
                         "근거_공고": b.get("posting") or "", "근거_자소서": b.get("resume") or "", "판정": "", "메모": ""})
    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"{CSV.name}: {len(rows)}개 (판정 칸을 채워 주세요)")


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def score():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
    done = [r for r in rows if r["판정"].strip()]
    cnt = {k: sum(r["판정"].strip() == k for r in done) for k in ("적절", "애매", "부적절")}
    n = len(done)
    res = {"n": n, "total": len(rows), **cnt,
           "appropriate_rate": round(cnt["적절"] / n, 3) if n else None, "appropriate_ci95": wilson(cnt["적절"], n),
           "inappropriate_rate": round(cnt["부적절"] / n, 3) if n else None, "inappropriate_ci95": wilson(cnt["부적절"], n),
           "note": "Wilson 95% 구간. 표본이 작아 구간이 넓다."}
    (HERE / "task_judge_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(res)


if __name__ == "__main__":
    {"make": make, "score": score}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
