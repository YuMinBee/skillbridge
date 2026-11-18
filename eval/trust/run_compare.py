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
from collections import Counter
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
# 보고서 맨 위 요약에 올리는 숫자 3개 (팀장 일정 11-19: 칸 정확도 · 원문에 없는 근거 · 5번 반복 일치)
SUMMARY_METRICS = ["star_slot_acc", "fake_evidence_rate", "consistency_5runs"]
CASE_NAMES = {"full": "네 칸 다 있음", "no_R": "결과 없음", "no_T": "맡은 일 없음",
              "inflated": "꾸밈말만", "team_vague": "본인 몫 불분명", "short": "한두 문장"}


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


def verdict(d: dict | None, metric: str) -> str:
    """차이(우리 − 웹) 한 개를 문장으로. 유의하지 않으면 방향을 말하지 않는다(규칙 12)."""
    if not d or d["significant"] is None:
        return "계산 불가"
    if not d["significant"]:
        return "차이가 유의하지 않음"
    better = (d["ci"][0] < 0) if metric in M.LOWER_IS_BETTER else (d["ci"][0] > 0)
    return "**우리가 더 좋음 (유의)**" if better else "**우리가 더 나쁨 (유의)**"


def summary_lines(res: dict, systems: list) -> list:
    meta, met, diffs = res["_meta"], res["metrics"], res["diffs"]
    webs = [s for s in systems if s.startswith("web_")]
    L = ["## 요약", ""]
    if "ours" not in meta["systems"]:
        L += ["> 우리 방식 결과(`ours_star_{split}.jsonl`)가 아직 없다. 웹 방식 값만 있다.".format(split=meta["split"]), ""]
    for m in SUMMARY_METRICS:
        arrow = " (낮을수록 좋음)" if m in M.LOWER_IS_BETTER else ""
        L.append(f"- **{NAMES[m]}**{arrow}")
        if "ours" in meta["systems"]:
            L.append(f"  - 우리 방식: {fmt(met[m].get('ours'), m)}")
        for s in webs:
            line = f"  - {SYS_NAMES.get(s, s)}: {fmt(met[m].get(s), m)}"
            d = diffs.get(m, {}).get(s)
            if d:
                line += f" → 차이 {fmt_diff(d['ci'], m)}, {verdict(d, m)}"
            L.append(line)
    L += ["", "값은 `값 [95% 구간]`, 차이는 `우리 − 웹`. 구간이 0을 포함하면 유의하지 않음으로 쓰고, 발표 3번 슬라이드에 올리지 않는다(AGENTS 규칙 12).", ""]
    return L


def setup_lines(res: dict, systems: list) -> list:
    meta = res["_meta"]
    cases = meta.get("cases") or {}
    case_txt = ", ".join(f"{CASE_NAMES.get(c, c)}({c}) {n}" for c, n in cases.items())
    L = ["## 실험 설정", "",
         f"- **정답셋**: `gold_star_{meta['split']}.jsonl` 합성 경험 단락 {meta['n_gold']}개 "
         f"(사람 검토 완료 {meta.get('n_reviewed', '—')}개). 실제 이력서는 쓰지 않았다. 유형: {case_txt}.",
         "- 라벨 규칙: `eval/trust/LABELING.md`. 칸(S·T·A·R)마다 있음/없음, 결과의 수치 성과 여부, 본인 역할이 분명한지.",
         "- **같은 모델로 비교한다.** 차이는 모델이 아니라 시스템(검색·규칙·검증)에서 나온다.", ""]
    L += ["| 방식 | 답한 모델 | 프롬프트 | temperature | 반복 | 웹 답변을 JSON으로 옮긴 모델 |", "|---|---|---|---|---|---|"]
    for s in systems:
        info = meta["systems"][s]
        rep = f"{info['n_runs'] / info['n_ids']:.1f}회" if info["n_ids"] else "—"
        L.append(f"| {SYS_NAMES.get(s, s)} | {info.get('model') or '—'} | {info.get('prompt_style') or '—'} | "
                 f"{info.get('temperature', '—') if info.get('temperature') is not None else '—'} | {rep} | {info.get('parse_model') or '—'} |")
    L += ["",
          "- 웹 ① 그냥 묻기: 사람이 웹 채팅에 그냥 치는 말(\"STAR로 분석해 주세요\"). 웹 ② 잘 쓴 프롬프트: 칸마다 원문 그대로 인용, 없으면 '없음', 지어내지 않기를 직접 요구.",
          "  둘 다 사용자 메시지 하나이고 검색·카탈로그·검증은 없다(웹 채팅에서 사용자가 할 수 있는 것은 프롬프트뿐). 문구는 `baseline_web.py`.",
          "- temperature 1 = 웹 채팅 기본값(매번 조금씩 다른 답), 0 = 가장 일정한 설정.",
          f"- 95% 구간: 단락(id) 단위 부트스트랩 {meta['n_boot']}회, 시드 {meta['seed']}. 같은 단락의 반복은 독립이 아니므로 단락을 다시 뽑는다. 차이는 같은 표본으로 둘 다 계산하는 대응 부트스트랩.",
          ""]
    return L


def limit_lines(res: dict) -> list:
    meta = res["_meta"]
    L = ["## 한계", "",
         "- **합성 데이터다.** 단락은 유형별로 만든 합성 문장이라 실제 이력서보다 정돈돼 있다. 실제 이력서에서의 정확도는 이보다 낮을 수 있다.",
         "- **웹 답변 채점은 LLM이 옮긴 것이다.** 자유 글 답변을 FAST 모델이 JSON으로 옮긴다(답변만 보고, 이력서·정답은 보지 않음). 옮기는 과정의 오류가 웹 점수에 섞일 수 있다. 원문 답변은 예측 파일에 그대로 남겨 다시 옮길 수 있다(`baseline_web.py --reparse`).",
         "- 웹 답변의 '부족하지만 있음'은 있음, '언급 안 함'은 없음으로 본다. 해석을 바꾸면 웹 점수가 달라진다.",
         "- 실제 claude.ai 웹이 아니라 Bedrock의 같은 모델에 같은 문장을 보낸 것이다(웹 화면은 발표 슬라이드 1의 캡처로 따로 보여 준다).",
         "- 정답은 1차 라벨러 1명 기준이다. 사람끼리 얼마나 일치하는지는 2차 라벨(사람 A–B)로 따로 본다."]
    if not res.get("human_ab"):
        L.append("  - 이번 실행에는 2차 라벨(`gold_star_b.jsonl`)이 없어 사람 A–B 일치도가 빠졌다.")
    else:
        L.append(f"  - 2차 라벨 {res['human_ab']['n']}개로 사람 A–B 일치도를 함께 적었다.")
    if meta["split"] == "test":
        L.append("- test는 마지막에 한 번만 열었다(`--final`). 개발 중 확인은 dev로만 했다(과적합 방지, AGENTS 규칙 9).")
    miss = {s: i["missing"] for s, i in meta["systems"].items() if i.get("missing")}
    if miss:
        L.append("- 결측(호출 실패·파싱 실패)이 있었다: " + ", ".join(f"{SYS_NAMES.get(s, s)} {n}건" for s, n in miss.items())
                 + ". 결측은 지표에서 빠진다.")
    if "ours" in meta["systems"] and not meta["systems"]["ours"].get("note"):
        L.append("- 우리 방식의 실행 조건(캐시 사용 여부 등)이 기록되지 않았다. 캐시를 켜고 반복하면 일치율이 당연히 100%가 되므로 `--ours-note`로 남긴다.")
    L.append("")
    return L


def write_report(path: Path, res: dict):
    meta, met, diffs = res["_meta"], res["metrics"], res["diffs"]
    systems = [s for s in ["ours", "web_plain_t1", "web_plain_t0", "web_good_t1", "web_good_t0"] if s in meta["systems"]]
    systems += [s for s in meta["systems"] if s not in systems]
    L = [f"# STAR 비교: 웹 방식 vs 우리 방식 ({meta['split']})", "",
         f"생성 {meta['at']} · 정답 단락 {meta['n_gold']}개 · 부트스트랩 {meta['n_boot']}회(단락 단위) · 표기 `값 [95% 구간]`", ""]
    if meta["split"] == "dev":
        L += ["> dev 결과다. 개발 중 확인용이며 **발표 숫자가 아니다**. 발표 숫자는 test(`report.md`).", ""]
    L += summary_lines(res, systems)
    L += setup_lines(res, systems)
    L += ["## 결과 (전체 지표)", "", "| 지표 | " + " | ".join(SYS_NAMES.get(s, s) for s in systems)
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
    L += [""] + limit_lines(res)
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
        first = next(iter(read_jsonl(path)), {})  # 실행 조건(모델·프롬프트·temperature)은 첫 줄에서
        for k in ("model", "prompt_style", "temperature", "parse_model"):
            if first.get(k) is not None:
                meta_sys[name][k] = first[k]
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
                     "cases": dict(Counter(gold[i].get("case") for i in ids)),
                     "n_reviewed": sum(1 for i in ids if gold[i].get("reviewed")),
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
