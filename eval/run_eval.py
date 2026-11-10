"""M5 평가: `make eval` / `.\\tasks.ps1 eval` 한 번으로 eval/report.md와 eval/results.json을 만든다.

1. 공고 스킬 추출 — gold_postings.jsonl (잡알리오 실공고 30건) · P/R/F1 · ablation
2. 이력서 갭 탐지 — synthetic_candidates.jsonl (갭을 심은 30명) · 갭 recall, 오탐률, 상태 정확도
3. 과정 추천 — gold_courses.jsonl (고용24 실카탈로그) · Hit@3, nDCG@5, 카탈로그 커버리지
4. 공고만 본 추천 vs 기업 기준 추천 — 같은 지원자, 같은 정답 상태로 경로 비교
5. 라벨 일치도 — gold_postings_b.jsonl(2차 라벨)이 있으면 Cohen's kappa

Bedrock 단계(llm_*)는 --live일 때만 호출하고, 결과를 eval/predictions/에 저장한다.
--live 없이 돌리면 저장된 예측으로 같은 표를 다시 만든다 (오프라인 재현).
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "eval"
PRED = EV / "predictions"

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true", help="Bedrock 단계를 실제로 호출 (aws sso login 필요)")
ARGS = ap.parse_args()
os.environ["BEDROCK_MOCK"] = "0" if ARGS.live else "1"
os.environ["DATA_MODE"] = "live"
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline import extract  # noqa: E402
from app.pipeline.recommend import _rank, build_path  # noqa: E402
from app.pipeline.score import STATUS_VALUE, readiness  # noqa: E402
from app.data import courses  # noqa: E402
from app.skills import get_dict  # noqa: E402


def jl(name):
    p = EV / name
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if p.exists() else []


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def cached(stage: str, items: list[dict], fn):
    """Bedrock 단계: --live면 호출해서 저장, 아니면 저장본을 읽는다. 없으면 None."""
    path = PRED / f"{stage}.json"
    if not ARGS.live:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    out, t0 = {}, time.time()
    for it in items:
        out[it["id"]] = fn(it)
    PRED.mkdir(exist_ok=True)
    path.write_text(json.dumps({"_meta": {"at": time.strftime("%Y-%m-%d %H:%M"), "sec": round(time.time() - t0, 1),
                                          "model": os.getenv("MODEL_ID", "")}, **out}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return out


# ── 1. 공고 추출 ─────────────────────────────────────────
def eval_postings():
    gold = jl("gold_postings.jsonl")
    stages = {"dict": ("① 별칭 사전만", lambda r: {m["skill_id"]: m["requirement"] for m in extract.extract_posting(r["text"])})}
    llm = {
        "llm_dict": ("② LLM 추출 + 사전", dict(use_embedding=False, use_llm=False)),
        "llm_embed": ("③ + 임베딩 후보 (top-1)", dict(use_embedding=True, use_llm=False)),
        "llm_full": ("④ + LLM 재랭킹 (운영 설정)", dict(use_embedding=True, use_llm=True)),
    }
    preds = {"dict": {r["id"]: stages["dict"][1](r) for r in gold}}
    for k, (_, kw) in llm.items():
        p = cached(f"postings_{k}", gold, lambda r, kw=kw: {m["skill_id"]: m["requirement"]
                                                            for m in extract.extract_posting_llm(r["text"], **kw)})
        if p is not None:
            preds[k] = p
    labels = {"dict": stages["dict"][0], **{k: v[0] for k, v in llm.items()}}
    rows = []
    for k, label in labels.items():
        if k not in preds:
            rows.append({"stage": k, "label": label, "available": False})
            continue
        tp = fp = fn = req_ok = 0
        by = {"hint": [0, 0, 0], "random": [0, 0, 0]}
        clean_fp = 0  # 라벨이 0개인 공고에서 무언가를 뽑은 공고 수
        errors = []
        for r in gold:
            g, p = r["labels"], preds[k].get(r["id"], {})
            t = len(set(g) & set(p)); f = len(set(p) - set(g)); n = len(set(g) - set(p))
            tp += t; fp += f; fn += n
            by[r["stratum"]][0] += t; by[r["stratum"]][1] += f; by[r["stratum"]][2] += n
            req_ok += sum(g[s] == p[s] for s in set(g) & set(p))
            if not g and p:
                clean_fp += 1
            for s in set(p) - set(g):
                errors.append({"id": r["id"], "type": "FP", "skill": s})
            for s in set(g) - set(p):
                errors.append({"id": r["id"], "type": "FN", "skill": s})
        P, R, F = prf(tp, fp, fn)
        rows.append({"stage": k, "label": label, "available": True, "p": P, "r": R, "f1": F, "tp": tp, "fp": fp, "fn": fn,
                     "req_acc": req_ok / tp if tp else 0.0,
                     "f1_hint": prf(*by["hint"])[2], "f1_random": prf(*by["random"])[2],
                     "clean_fp": clean_fp, "n_clean": sum(not r["labels"] for r in gold), "errors": errors})
    return {"n": len(gold), "n_labels": sum(len(r["labels"]) for r in gold),
            "labels_by": {k: sum(len(r["labels"]) for r in gold if r["stratum"] == k) for k in ("hint", "random")},
            "n_oov": sum(len(r["oov"]) for r in gold), "rows": rows}


# ── 2. 이력서 갭 ─────────────────────────────────────────
def _company(t):
    return json.loads((ROOT / f"seed/companies/{t}.json").read_text(encoding="utf-8"))


def gap_metrics(cands, preds):
    gap_tp = gap_n = own_fp = own_n = st_ok = st_n = 0
    oov_ok = oov_n = 0
    mae = []
    for c in cands:
        reqs = _company(c["company"])["requirements"]
        p = {s: v["status"] if isinstance(v, dict) else v for s, v in preds.get(c["id"], {}).items()}
        for sid, gs in c["gold_status"].items():
            ps = p.get(sid, "miss")
            st_n += 1; st_ok += ps == gs
            if gs != "own":
                gap_n += 1; gap_tp += ps != "own"
            else:
                own_n += 1; own_fp += ps != "own"
            v = c["variants"].get(sid)
            if v and not v["in_dict"]:
                oov_n += 1; oov_ok += ps == gs
        gm = {s: {"status": st} for s, st in c["gold_status"].items()}
        pm = {s: {"status": p.get(s, "miss")} for s in reqs}
        mae.append(abs(readiness(reqs, gm) - readiness(reqs, pm)))
    return {"gap_recall": gap_tp / gap_n, "false_gap": own_fp / own_n, "status_acc": st_ok / st_n,
            "oov_acc": oov_ok / oov_n if oov_n else None, "n_oov": oov_n, "readiness_mae": sum(mae) / len(mae),
            "gap_n": gap_n, "own_n": own_n}


def eval_gaps():
    cands = jl("synthetic_candidates.jsonl")
    labels = {"dict": "① 별칭 사전 + 규칙 판정",
              "llm_dict": "② LLM 추출 + 사전", "llm_embed": "③ + 임베딩 후보 (top-1)",
              "llm_full": "④ + LLM 재랭킹", "llm_full_net": "⑤ ④ + 사전 안전망 (운영 설정)"}
    kws = {"llm_dict": dict(use_embedding=False, use_llm=False, safety_net=False),
           "llm_embed": dict(use_embedding=True, use_llm=False, safety_net=False),
           "llm_full": dict(safety_net=False), "llm_full_net": dict()}
    preds = {"dict": {c["id"]: {s: v["status"] for s, v in extract.extract_resume(c["resume"]).items()} for c in cands}}
    for k, kw in kws.items():
        p = cached(f"resumes_{k}", cands, lambda c, kw=kw: {s: v["status"] for s, v in
                                                            extract.extract_resume_llm(c["resume"], **kw)[0].items()})
        if p is not None:
            preds[k] = p
    rows = [{"stage": k, "label": lab, "available": k in preds, **(gap_metrics(cands, preds[k]) if k in preds else {})}
            for k, lab in labels.items()]
    n_m = sum(len(c["variants"]) for c in cands)
    return {"n": len(cands), "mentions": n_m, "oov": sum(not v["in_dict"] for c in cands for v in c["variants"].values()),
            "rows": rows}


# ── 3. 과정 추천 ─────────────────────────────────────────
def _dcg(rels):
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


def eval_courses():
    gold = {g["skill_id"]: g["relevance"] for g in jl("gold_courses.jsonl")}
    cat = courses()
    out = {"ours": [], "catalog_order": []}
    covered, per = 0, []
    for sid, rel in gold.items():
        cands = [c for c in cat if sid in c["skills"]]
        if not rel:
            per.append({"skill": sid, "n": 0})
            continue
        covered += any(v >= 2 for v in rel.values())
        orders = {"ours": sorted(cands, key=_rank("대경권", sid)), "catalog_order": cands}
        row = {"skill": sid, "n": len(cands)}
        for k, lst in orders.items():
            rs = [rel.get(c["id"], 0) for c in lst]
            ideal = sorted(rel.values(), reverse=True)
            hit = any(r >= 2 for r in rs[:3])
            nd = _dcg(rs[:5]) / (_dcg(ideal[:5]) or 1)
            p1 = rs[0] >= 2 if rs else False
            out[k].append((hit, nd, p1))
            row[k] = {"hit3": hit, "ndcg5": round(nd, 3), "top1": lst[0]["title"] if lst else ""}
        per.append(row)
    agg = {k: {"hit3": sum(h for h, _, _ in v) / len(v), "ndcg5": sum(n for _, n, _ in v) / len(v),
               "p1": sum(p for _, _, p in v) / len(v), "n": len(v)} for k, v in out.items()}
    return {"skills": len(gold), "covered": covered, "agg": agg, "per_skill": per}


# ── 4. 공고만 본 추천 vs 기업 기준 ───────────────────────
def eval_baseline():
    sd = get_dict()
    res = {"company": [], "posting": []}
    missed_all, wasted_all = [], []
    for c in jl("synthetic_candidates.jsonl"):
        comp = _company(c["company"])
        reqs = comp["requirements"]
        gold_gaps = {s for s, st in c["gold_status"].items() if st != "own"}
        sm = {s: {"status": st} for s, st in c["gold_status"].items() if st != "miss"}
        for k, rq in (("company", reqs), ("posting", extract.posting_requirements(comp.get("posting_text", "")))):
            path = build_path(rq, sm, comp, 10)
            steps = [s["skill_id"] for s in path["steps"]]
            top3 = steps[:3]
            hit = sum(s in gold_gaps for s in top3) / len(top3) if top3 else 0.0
            covered = {s for s in steps if s in gold_gaps}
            res[k].append({"hit3": hit, "gap_cov": len(covered) / len(gold_gaps) if gold_gaps else 1.0,
                           "waste": sum(s not in reqs for s in steps) / len(steps) if steps else 0.0,
                           "hours": path["total_hours"]})
            if k == "posting":
                missed_all += [sd.name(s) for s in gold_gaps - covered]
                wasted_all += [sd.name(s) for s in set(steps) if s not in reqs]
    agg = {k: {m: sum(x[m] for x in v) / len(v) for m in ("hit3", "gap_cov", "waste", "hours")} for k, v in res.items()}
    from collections import Counter
    return {"agg": agg, "n": len(res["company"]), "top_missed": Counter(missed_all).most_common(5),
            "top_wasted": Counter(wasted_all).most_common(5)}


# ── 5. 라벨 일치도 ───────────────────────────────────────
def eval_agreement():
    a = {r["id"]: r for r in jl("gold_postings.jsonl")}
    b = {r["id"]: r for r in jl("gold_postings_b.jsonl")}
    common = [i for i in a if i in b and b[i].get("labels") is not None]
    if not common:
        return {"available": False}
    # 결정 단위: (공고, 두 라벨러 중 누구라도 붙인 스킬) → 붙였나/안 붙였나. 0/0 공고는 '라벨 없음'에 동의한 1건으로 센다
    pairs = []
    for i in common:
        u = set(a[i]["labels"]) | set(b[i]["labels"])
        if not u:
            pairs.append((0, 0))
        pairs += [(int(s in a[i]["labels"]), int(s in b[i]["labels"])) for s in u]
    n = len(pairs)
    po = sum(x == y for x, y in pairs) / n
    pa, pb = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return {"available": True, "postings": len(common), "decisions": n, "agree": po,
            "kappa": (po - pe) / (1 - pe) if pe < 1 else 1.0, "annotator_b": b[common[0]].get("annotator", "")}


# ── 보고서 ───────────────────────────────────────────────
def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def f3(x):
    return f"{x:.3f}"


def report(R):
    po, ga, co, ba, ag = R["postings"], R["gaps"], R["courses"], R["baseline"], R["agreement"]
    L = [f"# 역량다리 평가 보고서", "",
         f"생성: {R['at']} · 명령: `python eval/run_eval.py{' --live' if R['live'] else ''}` · 정답셋은 `eval/`, 라벨 규칙은 [LABELING.md](LABELING.md)", "",
         "> 정답 라벨 1차는 AI 보조 초안(`claude-draft`)이고 팀원 2차 라벨로 검수·일치도를 잽니다. "
         "2차 라벨 전까지 아래 수치는 **잠정**입니다.", "",
         f"## 1. 공고 스킬 추출 (잡알리오 실공고 {po['n']}건 · 정답 {po['n_labels']}개 · 사전 밖 언급 {po['n_oov']}개)", "",
         f"| 단계 | Precision | Recall | F1 | 필수/우대 일치 | F1 (단서 20건 · 정답 {po['labels_by']['hint']}) | "
         f"F1 (무작위 10건 · 정답 {po['labels_by']['random']}) | 라벨 0개 공고 오탐 |",
         "|---|---|---|---|---|---|---|---|"]
    for r in po["rows"]:
        if not r["available"]:
            L.append(f"| {r['label']} | — | — | — | — | — | — | Bedrock 실행 전 (`--live`) |")
            continue
        L.append(f"| {r['label']} | {f3(r['p'])} | {f3(r['r'])} | **{f3(r['f1'])}** | {pct(r['req_acc'])} | {f3(r['f1_hint'])} | "
                 f"{f3(r['f1_random'])} | {r['clean_fp']}/{r['n_clean']} |")
    d = next(r for r in po["rows"] if r["stage"] == "dict")
    L += ["", f"사전만 쓸 때 놓친 것(FN) {d['fn']}개 · 잘못 뽑은 것(FP) {d['fp']}개. 오류 목록은 `results.json`의 `errors`. "
          "무작위 10건은 정답이 거의 없어 F1보다 '라벨 0개 공고 오탐'(없는 스킬을 지어내는지)을 보는 용도입니다.", ""]

    L += [f"## 2. 이력서 갭 탐지 (합성 지원자 {ga['n']}명 · 언급 {ga['mentions']}개 중 사전 밖 표기 {ga['oov']}개)", "",
          "| 단계 | 갭 recall | 오탐률(보유→갭) | 상태 정확도(4종) | 사전 밖 표기 정확도 | 준비도 오차(MAE, 점) |",
          "|---|---|---|---|---|---|"]
    for r in ga["rows"]:
        if not r["available"]:
            L.append(f"| {r['label']} | — | — | — | — | Bedrock 실행 전 |")
            continue
        L.append(f"| {r['label']} | **{pct(r['gap_recall'])}** | {pct(r['false_gap'])} | {pct(r['status_acc'])} | "
                 f"{pct(r['oov_acc'])} | {r['readiness_mae']:.1f} |")
    L += ["", "갭 recall은 심어 둔 갭(보유가 아닌 요구역량)을 갭으로 잡은 비율, 오탐률은 실제 보유인데 갭으로 본 비율입니다.", ""]

    a = co["agg"]
    L += [f"## 3. 과정 추천 (고용24 실카탈로그 · 기업 요구 스킬 {co['skills']}개)", "",
          "| 순위 방식 | Hit@3 | nDCG@5 | 1순위 적합 |", "|---|---|---|---|",
          f"| 역량다리 순위 (주제 일치 → 지역 → 기초 → 짧은 순) | **{pct(a['ours']['hit3'])}** | {f3(a['ours']['ndcg5'])} | {pct(a['ours']['p1'])} |",
          f"| 카탈로그 순서 그대로 (기준선) | {pct(a['catalog_order']['hit3'])} | {f3(a['catalog_order']['ndcg5'])} | {pct(a['catalog_order']['p1'])} |",
          "", f"카탈로그 커버리지: {co['skills']}개 중 적합 과정이 있는 스킬 {co['covered']}개. "
          f"과정이 없는 스킬({', '.join(p['skill'] for p in co['per_skill'] if p['n'] == 0)})은 자습·기업 트랙으로 대체합니다.", ""]

    b = ba["agg"]
    L += [f"## 4. 공고만 본 추천 vs 기업 기준 추천 (같은 지원자 {ba['n']}명, 정답 상태 사용)", "",
          "| 기준 | 경로 상위 3단계 적중 | 실제 갭 커버율 | 불필요한 단계 | 평균 경로 시간 |", "|---|---|---|---|---|",
          f"| 기업 등록 기준 (역량다리) | **{pct(b['company']['hit3'])}** | **{pct(b['company']['gap_cov'])}** | {pct(b['company']['waste'])} | {b['company']['hours']:.0f}h |",
          f"| 공고 문구만 | {pct(b['posting']['hit3'])} | {pct(b['posting']['gap_cov'])} | {pct(b['posting']['waste'])} | {b['posting']['hours']:.0f}h |",
          "", "공고만 볼 때 가장 많이 놓친 갭: " + ", ".join(f"{n}({c})" for n, c in ba["top_missed"]),
          "", "공고만 볼 때 생긴 불필요한 공부: " + (", ".join(f"{n}({c})" for n, c in ba["top_wasted"]) or "없음"), ""]

    L += ["## 5. 라벨 일치도", ""]
    if ag["available"]:
        L.append(f"공고 {ag['postings']}건 · 결정 {ag['decisions']}개 · 일치율 {pct(ag['agree'])} · **Cohen's κ = {ag['kappa']:.2f}** "
                 f"(2차 라벨: {ag['annotator_b']})")
    else:
        L.append("2차 라벨(`eval/gold_postings_b.jsonl`)을 기다리는 중. 만드는 방법은 LABELING.md 4절.")
    L += ["", "## 6. 사용자 평가", "", "5~10명 5점 척도 설문은 `eval/SURVEY.md` 문항으로 진행 예정 (결과는 `eval/survey.csv`).", "",
          "## 한계", "",
          "- 공공기관 공고는 본문이 첨부파일에 있는 경우가 많아, 자격요건·우대사항 필드만 평가했습니다.",
          "- 공고 표본 20건은 디지털 단서 정규식으로 골랐습니다(나머지 10건 무작위). 단서가 사전 별칭과 겹쳐 재현율이 실제보다 높게 나올 수 있습니다.",
          "- 합성 지원자는 템플릿 문장이라 실제 이력서보다 쉽습니다. 사전 밖 표기 비율로 난이도를 보완했습니다.",
          "- 과정 적합도는 과정 제목 기준 판단입니다 (상세 커리큘럼 미확인)."]
    return "\n".join(L) + "\n"


def main():
    R = {"at": time.strftime("%Y-%m-%d %H:%M"), "live": ARGS.live,
         "postings": eval_postings(), "gaps": eval_gaps(), "courses": eval_courses(),
         "baseline": eval_baseline(), "agreement": eval_agreement()}
    (EV / "results.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (EV / "report.md").write_text(report(R), encoding="utf-8")
    d = next(r for r in R["postings"]["rows"] if r["stage"] == "dict")
    g = next(r for r in R["gaps"]["rows"] if r["stage"] == "dict")
    print(f"공고 추출 F1(사전) {d['f1']:.3f} · 갭 recall(사전) {g['gap_recall']:.1%} · "
          f"Hit@3 {R['courses']['agg']['ours']['hit3']:.1%} → eval/report.md")


if __name__ == "__main__":
    main()
