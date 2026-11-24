"""민감도: 웹 답변의 '부족하지만 있음'(weak)을 있음(보고서 기준) / 없음으로 볼 때 지표가 어떻게 바뀌는가.
저장된 test 예측만 읽는다(모델 호출 없음). 결과: results_sensitivity.json
    python eval/trust/sensitivity_weak.py
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import metrics as M  # noqa: E402
import run_compare as RC  # noqa: E402

N = 2000
P = HERE / "predictions"
WEBS = {"웹 ① 그냥 묻기 t=1": "web_star_test_plain_t1.jsonl", "웹 ② 잘 쓴 프롬프트 t=0": "web_star_test_good_t0.jsonl",
        "웹 ③ 같은 칸 기준 t=0": "web_star_test_strict_t0.jsonl"}


def main():
    gold = RC.load_gold("test")
    ids = sorted(gold)
    ours, _ = RC.load_preds(P / "ours_star_test.jsonl", M.norm_ours)
    out = {}
    for label, weak in (("weak=있음(보고서 기준)", True), ("weak=없음", False)):
        M.WEB_PRESENT["weak"] = weak
        rows = {"우리 방식": {"acc": M.boot(M.slot_acc, gold, ours, ids, n=N), "fake": M.boot(M.fake_evidence, gold, ours, ids, n=N),
                           "consistency": M.consistency(ours, ids)}}
        for name, f in WEBS.items():
            w, _ = RC.load_preds(P / f, M.norm_web)
            d = M.boot_diff(M.fake_evidence, gold, ours, w, ids, n=N)
            rows[name] = {"acc": M.boot(M.slot_acc, gold, w, ids, n=N), "fake": M.boot(M.fake_evidence, gold, w, ids, n=N),
                          "fake_ours_minus_web": d, "fake_diff_significant": M.significant(d),
                          "consistency": M.consistency(w, ids)}
        out[label] = rows
    M.WEB_PRESENT["weak"] = True
    (HERE / "results_sensitivity.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    pct = lambda v: f"{v[0] * 100:.1f}% [{v[1] * 100:.1f}, {v[2] * 100:.1f}]"  # noqa: E731
    for label, rows in out.items():
        print("==", label)
        for name, r in rows.items():
            extra = f" · 우리−웹 {pct(r['fake_ours_minus_web'])} 유의 {r['fake_diff_significant']}" if "fake_ours_minus_web" in r else ""
            print(f"  {name}: 정확도 {pct(r['acc'])} · 없는 근거 {pct(r['fake'])}{extra} · 5번 일치 {r['consistency'] * 100:.1f}%")


if __name__ == "__main__":
    main()
