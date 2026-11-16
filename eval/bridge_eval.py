"""'연결되는 경험'이 너무 너그러운지 잰다 (합성 지원자 30명, 정답 상태).

    python eval/bridge_eval.py --live   # Bedrock(경험 연결) 호출 후 eval/predictions/bridge_links.json 저장
    python eval/bridge_eval.py          # 저장본으로 다시 계산

추출 결과는 저장된 운영 설정 예측(predictions/resumes_llm_full_net.json)을 쓰고, 그 위에 bridge만 더한다.
- 잘못 준 점수: 정답 '없음'인 요구 기술에 0.5를 준 비율 (낮을수록 좋음)
- 되찾은 점수: 정답 '부분·검증·보유'인데 추출이 놓친 요구 기술을 다시 찾은 비율 (높을수록 좋음)
갭 recall(보유가 아닌 것을 갭으로 잡는가)은 bridge가 '보유'를 주지 않으므로 바뀌지 않는다.
"""
import argparse, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
ap = argparse.ArgumentParser(); ap.add_argument("--live", action="store_true"); A = ap.parse_args()

from app.pipeline import bridge, implies  # noqa: E402
from app.skills import get_dict  # noqa: E402

EV = ROOT / "eval"
cands = [json.loads(l) for l in open(EV / "synthetic_candidates.jsonl", encoding="utf-8") if l.strip()]
pred = json.loads((EV / "predictions/resumes_llm_full_net.json").read_text(encoding="utf-8"))
out_f = EV / "predictions/bridge_links.json"
saved = json.loads(out_f.read_text(encoding="utf-8")) if out_f.exists() else {}
sd = get_dict()

rows = []
for c in cands:
    comp = json.loads((ROOT / f"seed/companies/{c['company']}.json").read_text(encoding="utf-8"))
    targets = sorted(set(comp.get("requirements") or {}) | set(comp.get("apply_requirements") or {}))
    sm = {s: {"status": st, "evidence": ""} for s, st in pred[c["id"]].items()}
    sm, _ = implies.expand(sm)  # 실제 파이프라인 순서: 상하위 보완 → 연결되는 경험
    found = set(sm)
    sm, sim = bridge.similar(sm, targets)
    if A.live:
        _, links = bridge.link(c["resume"], sm, targets, {k: sd.name(k) for k in targets})
        saved[c["id"]] = links
    links = saved.get(c["id"], [])
    for x in links:
        sm.setdefault(x["skill_id"], {"status": "verify"})
    bridged = {s for s, _ in sim} | {x["skill_id"] for x in links}
    for s in targets:
        if s in found:
            continue  # 추출이 이미 찾은 기술은 bridge 대상이 아니다
        gold = c["gold_status"].get(s, "miss")
        rows.append({"cid": c["id"], "skill": s, "gold": gold, "bridged": s in bridged,
                     "how": "similar" if s in {a for a, _ in sim} else ("link" if s in bridged else "")})
if A.live:
    out_f.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")


def rate(rs): return (sum(r["bridged"] for r in rs) / len(rs)) if rs else float("nan")


def boot(rs):
    by = {}
    for r in rs: by.setdefault(r["cid"], []).append(r)
    ks = list(by); random.seed(6); v = []
    for _ in range(2000):
        s = [r for k in (random.choice(ks) for _ in ks) for r in by[k]]
        if s: v.append(rate(s))
    v.sort(); return v[int(.025 * len(v))], v[int(.975 * len(v))]


wrong = [r for r in rows if r["gold"] == "miss"]
recover = [r for r in rows if r["gold"] != "miss"]
lo, hi = boot(wrong)
print(f"추출이 놓친 요구 기술 {len(rows)}개 (지원자 {len(cands)}명)")
print(f"잘못 준 점수: 정답 '없음' {len(wrong)}개 중 {sum(r['bridged'] for r in wrong)}개 = {rate(wrong):.1%} (95% 구간 {lo:.1%}–{hi:.1%})")
print(f"되찾은 점수: 정답 '있음' {len(recover)}개 중 {sum(r['bridged'] for r in recover)}개 = {rate(recover):.1%}")
for r in wrong:
    if r["bridged"]:
        ev = next((x for x in saved.get(r["cid"], []) if x["skill_id"] == r["skill"]), {})
        print(f"  ✗ {r['cid']} {r['skill']} ({r['how']}) {ev.get('evidence', '')[:50]} | {ev.get('reason', '')[:50]}")
