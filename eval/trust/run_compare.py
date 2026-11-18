"""웹 방식 vs 우리 방식 STAR 비교 → results + report. 지표 정의는 metrics.py.

읽는 파일 (eval/trust/predictions/)
- web_star_{split}_{plain|good}_t{0|1}.jsonl : baseline_web.py 결과 (있는 것만)
- ours_star_{split}.jsonl                    : 우리 방식. 한 줄 = {"id", "run", "result": star.diagnose() 반환값}
- eval/trust/gold_star_b.jsonl               : 2차 라벨(있으면 사람 A–B 일치도)

쓰는 파일
- dev  → results_dev.json, report_dev.md   (개발 중 확인용. 발표 숫자 아님)
- test → results.json, report.md           (CONTRACTS 6절. T4 화면이 읽음. --final로 마지막 한 번)

사용
  python eval/trust/run_compare.py --split dev
  python eval/trust/run_compare.py --split dev --mock        # *_mock.jsonl로 형식 확인
  python eval/trust/run_compare.py --split test --final
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import metrics as M  # noqa: E402

PRED = HERE / "predictions"
BASE_WEB = "web_plain_t1"   # 결과의 "web" = 사람이 웹에 그냥 묻는 방식(기본 temperature)

NAMES = {
    "star_slot_acc": "STAR 칸 정확도",
    "star_slot_kappa": "STAR 칸 κ",
    "fake_evidence_rate": "없는 근거를 있다고 한 비율",
    "consistency_5runs": "5번 반복 모두 같은 판정",
    "inflated_false_strong": "꾸민 말에 '강함' 판정",
    "quote_verbatim_rate": "(참고) 근거가 원문 그대로",
}
SYS_NAMES = {"ours": "우리 방식", "web_plain_t1": "웹 ① 그냥 묻기 t=1", "web_plain_t0": "웹 ① 그냥 묻기 t=0",
             "web_good_t1": "웹 ② 잘 쓴 프롬프트 t=1", "web_good_t0": "웹 ② 잘 쓴 프롬프트 t=0",
             "human_ab": "사람 A–B"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_gold(split: str) -> dict:
    return {r["id"]: r for r in read_jsonl(HERE / f"gold_star_{split}.jsonl") if r.get("labeler", "A") == "A"}


def load_preds(path: Path, norm) -> tuple[dict, int]:
    """id → [정규화 예측, run 순서]. 같은 (id, run)이 여러 줄이면 마지막 줄. 결측 개수도 돌려준다."""
    by = {}
    for r in read_jsonl(path):
        by[(r["id"], r.get("run", 1))] = r
    preds, missing = {}, 0
    for (i, _run), r in sorted(by.items(), key=lambda x: (x[0][0], x[0][1])):
        p = norm(r)
        if p is None:
            missing += 1
            continue
        preds.setdefault(i, []).append(p)
    return preds, missing


def find_systems(split: str, mock: bool) -> dict:
    sfx = "_mock" if mock else ""
    out = {}
    pat = re.compile(rf"^web_star_{split}_(plain|good)_t([0-9.]+){sfx}\.jsonl$")
    for f in sorted(PRED.glob(f"web_star_{split}_*.jsonl")) if PRED.exists() else []:
        m = pat.match(f.name)
        if m:
            out[f"web_{m.group(1)}_t{m.group(2)}"] = (f, M.norm_web)
    ours = PRED / f"ours_star_{split}{sfx}.jsonl"
    if ours.exists():
        out["ours"] = (ours, M.norm_ours)
    return out


def human_ab(n_boot: int) -> dict | None:
    path = HERE / "gold_star_b.jsonl"
    if not path.exists():
        return None
    gold_a = {**load_gold("dev"), **load_gold("test")}
    b = {r["id"]: [M.norm_human(r)] for r in read_jsonl(path)
         if r.get("labeler") == "B" and all(v is not None for v in r["slots"].values())}
    ids = sorted(i for i in b if i in gold_a)
    if not ids:
        return None
    return {"n": len(ids),
            "star_slot_acc": M.boot(M.slot_acc, gold_a, b, ids, n=n_boot),
            "star_slot_kappa": M.boot(M.slot_kappa, gold_a, b, ids, n=n_boot)}


def pct(v):
    return "—" if v is None else f"{v * 100:.1f}%"


def fmt(ci, metric):
    if not ci or ci[0] is None:
        return "—"
    f = (lambda x: f"{x:.2f}") if metric == "star_slot_kappa" else pct
    lo = "" if ci[1] is None else f" [{f(ci[1])}, {f(ci[2])}]"
    return f"{f(ci[0])}{lo}"


def fmt_diff(ci, metric):
    if not ci or ci[0] is None:
        return "—"
    if metric == "star_slot_kappa":
        f = lambda x: f"{x:+.2f}"  # noqa: E731
    else:
        f = lambda x: f"{x * 100:+.1f}%p"  # noqa: E731
    return f"{f(ci[0])} [{f(ci[1])}, {f(ci[2])}]" if ci[1] is not None else f(ci[0])


def write_report(path: Path, res: dict):
    meta, met, diffs = res["_meta"], res["metrics"], res["diffs"]
    systems = [s for s in ["ours", "web_plain_t1", "web_plain_t0", "web_good_t1", "web_good_t0"] if s in meta["systems"]]
    systems += [s for s in meta["systems"] if s not in systems]
    L = [f"# STAR 비교: 웹 방식 vs 우리 방식 ({meta['split']})", "",
         f"생성 {meta['at']} · 정답 단락 {meta['n_gold']}개 · 부트스트랩 {meta['n_boot']}회(단락 단위) · 표기 `값 [95% 구간]`", ""]
    if meta["split"] == "dev":
        L += ["> dev 결과다. 개발 중 확인용이며 **발표 숫자가 아니다**. 발표 숫자는 test(`report.md`).", ""]
    L += ["## 결과", "", "| 지표 | " + " | ".join(SYS_NAMES.get(s, s) for s in systems)
          + (" | 사람 A–B |" if res.get("human_ab") else " |"),
          "|---|" + "---|" * (len(systems) + (1 if res.get("human_ab") else 0))]
    for m in M.METRICS:
        row = [fmt(met[m].get(s), m) for s in systems]
        if res.get("human_ab"):
            row.append(fmt(res["human_ab"].get(m), m) if m in ("star_slot_acc", "star_slot_kappa") else "")
        arrow = " ↓" if m in M.LOWER_IS_BETTER else ""
        L.append(f"| {NAMES[m]}{arrow} | " + " | ".join(row) + " |")
    L += ["", "↓ = 낮을수록 좋음.", ""]
    if diffs:
        L += ["## 차이 (우리 − 웹)", "", "구간이 0을 포함하면 **유의하지 않음**(AGENTS 규칙 12).", "",
              "| 지표 | 비교 | 차이 [95% 구간] | 판정 |", "|---|---|---|---|"]
        for m in M.METRICS:
            if m == "quote_verbatim_rate":
                continue
            for k, d in diffs.get(m, {}).items():
                sig = {True: "유의", False: "유의하지 않음", None: "계산 불가"}[d["significant"]]
                L.append(f"| {NAMES[m]} | {SYS_NAMES.get(k, k)} | {fmt_diff(d['ci'], m)} | {sig} |")
        L.append("")
    L += ["## 입력", "", "| 방식 | 파일 | 단락 | 판정 수 | 결측(실패·파싱 실패) |", "|---|---|---|---|---|"]
    for s, info in meta["systems"].items():
        L.append(f"| {SYS_NAMES.get(s, s)} | `{info['file']}` | {info['n_ids']} | {info['n_runs']} | {info['missing']} |")
    L += ["", "## 지표 정의", "",
          "- **STAR 칸 정확도**: S·T·A·R 칸 유무가 사람 정답과 같은 비율. 웹 답변의 '부족하지만 있음'은 있음, '언급 안 함'은 없음으로 본다.",
          "- **없는 근거를 있다고 한 비율**: 정답이 '없음'인 칸과 수치 성과 없는 결과를, 있다고 한 비율. 이력서에 없는 경험·성과를 지어낸 정도.",
          "- **5번 반복 모두 같은 판정**: 같은 단락을 5번 넣었을 때 S·T·A·R 판정이 5번 모두 같은 단락 비율.",
          "- **꾸민 말에 '강함' 판정**: 행동·결과 없이 꾸밈말만 있는 단락(case=inflated)에 강점이 강하다고 한 비율.",
          "- **(참고) 근거가 원문 그대로**: '있다'고 한 칸의 근거 문장이 원문에 글자 그대로 있는 비율. 웹 ①은 인용을 요구하지 않았으므로 핵심 지표로 쓰지 않는다.",
          "- 웹 답변(자유 글)은 FAST 모델이 답변만 보고 JSON으로 옮긴다(이력서·정답을 보지 않음). `baseline_web.py` 참고."]
    if "ours" in meta["systems"] and meta["systems"]["ours"].get("note"):
        L += [f"- 우리 방식: {meta['systems']['ours']['note']}"]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--final", action="store_true", help="test 실행 확인 (마지막 한 번)")
    ap.add_argument("--mock", action="store_true", help="*_mock.jsonl 예측으로 형식만 확인")
    ap.add_argument("--n-boot", type=int, default=M.N_BOOT)
    ap.add_argument("--ours-note", default="", help="보고서에 남길 우리 방식 실행 조건(예: '캐시 끄고 5회')")
    a = ap.parse_args()
    if a.split == "test" and not a.final:
        sys.exit("test는 마지막에 한 번만 본다(규칙 9). 정말이면 --final을 붙인다.")

    gold = load_gold(a.split)
    ids = sorted(gold)
    systems = find_systems(a.split, a.mock)
    if not systems:
        sys.exit(f"predictions/에 {a.split} 예측 파일이 없습니다. baseline_web.py부터 돌리세요.")

    preds, meta_sys = {}, {}
    for name, (path, norm) in systems.items():
        p, missing = load_preds(path, norm)
        unknown = set(p) - set(gold)
        if unknown:
            print(f"  경고: {path.name}에 정답셋에 없는 id {len(unknown)}개 (무시)")
        preds[name] = {i: v for i, v in p.items() if i in gold}
        meta_sys[name] = {"file": path.name, "n_ids": len(preds[name]),
                          "n_runs": sum(len(v) for v in preds[name].values()), "missing": missing}
        if name == "ours" and a.ours_note:
            meta_sys[name]["note"] = a.ours_note
        print(f"{name}: {path.name} · 단락 {len(preds[name])}/{len(ids)} · 결측 {missing}")

    metrics_out = {m: {} for m in M.METRICS}
    for m, fn in M.METRICS.items():
        for name, p in preds.items():
            metrics_out[m][name] = M.boot(fn, gold, p, ids, n=a.n_boot)
        if BASE_WEB in preds:
            metrics_out[m]["web"] = metrics_out[m][BASE_WEB]  # CONTRACTS 6절 모양(T4 화면)

    diffs = {}
    if "ours" in preds:
        for m, fn in M.METRICS.items():
            for name in sorted(preds, key=lambda n: (n.startswith("web_good"), n)):  # ① 그냥 묻기 먼저
                if name.startswith("web_"):
                    ci = M.boot_diff(fn, gold, preds["ours"], preds[name], ids, n=a.n_boot)
                    diffs.setdefault(m, {})[name] = {"ci": ci, "significant": M.significant(ci)}

    hab = human_ab(a.n_boot)
    if hab:
        metrics_out["star_slot_acc"]["human_ab"] = hab["star_slot_acc"]
        metrics_out["star_slot_kappa"]["human_ab"] = hab["star_slot_kappa"]

    res = {"_meta": {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "split": a.split,
                     "n": {"star": len(ids)}, "n_gold": len(ids), "n_boot": a.n_boot, "seed": M.SEED,
                     "base_web": BASE_WEB, "mock": a.mock, "systems": meta_sys},
           "metrics": metrics_out, "diffs": diffs, "human_ab": hab}

    stem = "" if a.split == "test" else "_dev"
    stem += "_mock" if a.mock else ""
    out_json, out_md = HERE / f"results{stem}.json", HERE / f"report{stem}.md"
    if out_json.exists():
        # 다른 트랙이 넣은 칸(retrieval 등)은 지우지 않는다
        old = json.loads(out_json.read_text(encoding="utf-8"))
        for k, v in old.items():
            res.setdefault(k, v)
        for k, v in (old.get("metrics") or {}).items():
            res["metrics"].setdefault(k, v)
    out_json.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(out_md, res)
    print(f"→ {out_json.name}, {out_md.name}")


if __name__ == "__main__":
    main()
