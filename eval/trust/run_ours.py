"""우리 방식(STAR 진단) → predictions/ours_star_{split}.jsonl. run_compare.py가 웹 방식과 비교한다.

한 줄 = {"id", "run", "result": star.diagnose() 결과(경험 목록), "meta": {mode, dropped_quotes, cached}}
- 정답 단락(gold_star_{split}.jsonl, labeler A)마다 --runs번(기본 5) 돌린다.
- **캐시를 끈다.** 캐시를 켜면 같은 입력에 같은 결과가 나와 '5번 반복 일치율'이 당연히 100%가 되므로, 시스템 자체의 일치율을 잰다.
  (서비스에서는 캐시가 켜져 있어 같은 문서는 항상 같은 결과다. 이 차이는 보고서에 --ours-note로 적는다.)
- 실제 Bedrock을 부른다(BEDROCK_MOCK=0 필요). 규칙 폴백이 섞이면 결과에 mode=rule로 남고 끝에 개수를 알린다.
- 이미 있는 (id, run)은 건너뛴다. 끊겨도 다시 돌리면 이어서 한다.

실행:
  python eval/trust/run_ours.py --split dev               # 30단락 × 5회 = 150회, 약 $1.5
  python eval/trust/run_ours.py --split dev --mock        # 규칙만, AWS 없이 형식 확인 → ours_star_dev_mock.jsonl
  python eval/trust/run_compare.py --split dev --ours-note "캐시 끔, Sonnet 4.6, temperature 0"
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRED = HERE / "predictions"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--mock", action="store_true", help="Bedrock 없이 규칙만 (형식 확인용)")
    ap.add_argument("--final", action="store_true", help="test split은 마지막에 한 번만 돌린다는 확인")
    a = ap.parse_args()
    if a.split == "test" and not a.final:
        raise SystemExit("test는 발표 숫자다. 마지막에 한 번만 --final로 돌린다.")

    os.environ["BEDROCK_MOCK"] = "1" if a.mock else os.environ.get("BEDROCK_MOCK", "0")
    sys.path.insert(0, str(ROOT / "backend"))
    os.chdir(ROOT / "backend")  # .env와 데이터 경로를 앱과 같게
    from app.adapters import bedrock  # noqa: E402
    from app.agents import star  # noqa: E402
    if not a.mock and bedrock.mode() != "bedrock":
        raise SystemExit("Bedrock 모드가 아니다. .env의 BEDROCK_MOCK=0, aws sso login --profile kosa 확인")

    gold = [json.loads(l) for l in (HERE / f"gold_star_{a.split}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    gold = [g for g in gold if g.get("labeler", "A") == "A"]
    out = PRED / f"ours_star_{a.split}{'_mock' if a.mock else ''}.jsonl"
    PRED.mkdir(exist_ok=True)
    done = set()
    if out.exists():
        for l in out.read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                done.add((r["id"], r["run"]))
    todo = [(g, k) for g in gold for k in range(1, a.runs + 1) if (g["id"], k) not in done]
    print(f"{a.split}: 단락 {len(gold)} × {a.runs}회, 남은 {len(todo)}개 → {out.relative_to(ROOT)}")

    lock, n_rule, usd, t0 = threading.Lock(), 0, 0.0, time.time()

    def one(g, k):
        log = bedrock.CallLog()
        res, meta = star.diagnose(g["text"], log=log, use_llm=not a.mock, cache=False)
        return g["id"], k, res, meta, log

    with ThreadPoolExecutor(a.workers) as ex, out.open("a", encoding="utf-8") as fh:
        futs = [ex.submit(one, g, k) for g, k in todo]
        for i, f in enumerate(as_completed(futs), 1):
            gid, k, res, meta, log = f.result()
            with lock:
                fh.write(json.dumps({"id": gid, "run": k, "result": res, "meta": meta}, ensure_ascii=False) + "\n")
                fh.flush()
                n_rule += meta.get("mode") == "rule" and not a.mock
                usd += _usd(log)
            if i % 10 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)}  {time.time() - t0:.0f}s  ${usd:.2f}")
    if n_rule:
        print(f"⚠ 규칙 폴백 {n_rule}건 (Bedrock 실패). 해당 줄을 지우고 다시 돌리면 그 부분만 재시도한다.")
    print("다음: python eval/trust/run_compare.py --split", a.split, '--ours-note "캐시 끔, temperature 0"')


def _usd(log) -> float:
    try:
        from app.agents import cost
        return sum(cost.usd(c) for c in getattr(log, "calls", []))
    except Exception:  # noqa: BLE001  비용 표시는 참고용
        return 0.0


if __name__ == "__main__":
    main()
