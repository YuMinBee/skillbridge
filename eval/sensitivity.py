"""점수 가중치 민감도: 필수 가중치(기본 2)와 부분·검증 상태값(기본 0.5)을 바꾸면 결론이 바뀌는가.
AWS 없이 돈다. 추출 오차를 빼려고 상태를 직접 준다.
- 합성 지원자 30명(gold_status)은 실제 회사 기준과 겹치는 기술이 적어 점수 42%가 0점(바닥 효과) → 참고로만 쓴다.
- 본 측정: 회사들이 요구하는 기술 전체에 상태를 무작위로 준 가상 지원자 300명(보유 35% · 부분 15% · 검증 15% · 없음 35%, 시드 0).
    python eval/sensitivity.py
볼 것: 점수 변화폭, 색 구간(70·40) 이동, 회사 순위 상관(Spearman), 할 일 순서(필수 먼저 정렬이라 구조상 불변).
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.data import hidden_ids, stats_only_ids  # noqa: E402
from app.pipeline import score  # noqa: E402
from app.pipeline.diagnose import effective_requirements  # noqa: E402

import random
skip = hidden_ids() | stats_only_ids()
comps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "seed/companies").glob("*.json"))]
comps = [c for c in comps if c["tenant_id"] not in skip and c.get("level") not in ("경력", "시니어")]
if "--gold" in sys.argv:
    cands = [json.loads(l) for l in open(ROOT / "eval/synthetic_candidates.jsonl", encoding="utf-8") if l.strip()]
else:
    uni = sorted({s for c in comps for k in ("apply_requirements", "requirements") for s in (c.get(k) or {})}
                 | {s for c in comps for g in (c.get("any_of") or []) for s in g})
    rnd = random.Random(0)
    cands = [{"id": f"r{i}", "gold_status": {s: rnd.choices(["own", "part", "verify", "miss"], [35, 15, 15, 35])[0] for s in uni}}
             for i in range(300)]


def band(v): return "hi" if v >= 70 else "mid" if v >= 40 else "lo"


def scores(must_w, part_v):
    score.STATUS_VALUE.update({"part": part_v, "verify": part_v})
    out = {}
    for cd in cands:
        st = {k: {"status": v} for k, v in cd["gold_status"].items()}
        for c in comps:
            for which in ("apply_requirements", "requirements"):
                req = effective_requirements(c, st, which=which) if c.get(which) else {}
                if not req: continue
                req = {s: (must_w if w == 2 else w) for s, w in req.items()}
                out[(cd["id"], c["tenant_id"], which)] = score.readiness(req, st)
    score.STATUS_VALUE.update({"part": 0.5, "verify": 0.5})
    return out


def spearman(a, b):
    n = len(a)
    if n < 3: return None
    def rk(x):
        o = sorted(range(n), key=lambda i: x[i]); r = [0.0] * n; i = 0
        while i < n:
            j = i
            while j + 1 < n and x[o[j + 1]] == x[o[i]]: j += 1
            for k in range(i, j + 1): r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = rk(a), rk(b); ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** .5; vb = sum((y - mb) ** 2 for y in rb) ** .5
    return cov / (va * vb) if va and vb else None


base = scores(2, 0.5)
rows = []
for name, mw, pv in [("필수 1.5", 1.5, .5), ("필수 3", 3, .5), ("필수 4", 4, .5), ("부분·검증 0.3", 2, .3), ("부분·검증 0.7", 2, .7)]:
    alt = scores(mw, pv)
    keys = [k for k in base if k in alt]
    d = [abs(alt[k] - base[k]) for k in keys]
    moved = sum(band(alt[k]) != band(base[k]) for k in keys)
    rhos = []
    for cd in cands:  # 같은 지원자에게 회사들을 실무 준비도로 줄 세운 순서가 유지되는가
        ks = [k for k in keys if k[0] == cd["id"] and k[2] == "requirements"]
        r = spearman([base[k] for k in ks], [alt[k] for k in ks])
        if r is not None: rhos.append(r)
    rows.append((name, sum(d) / len(d), max(d), moved / len(keys), sum(rhos) / len(rhos), min(rhos)))

print(f"지원자 {len(cands)}명 × 회사 {len(comps)}곳 (신입·인턴·미상, 서류+실무 점수 {len(base)}개) · 기준: 필수 2 / 우대 1 / 부분·검증 0.5")
print("| 바꾼 값 | 점수 변화 평균 | 최대 | 색 구간 바뀐 비율 | 회사 순위 상관 평균 | 최저 |")
print("|---|---|---|---|---|---|")
for n, m, mx, mv, rh, rmin in rows:
    print(f"| {n} | {m:.1f}점 | {mx}점 | {mv:.1%} | {rh:.3f} | {rmin:.3f} |")
print("할 일 순서: 필수 → 상태값 낮은 순 정렬이라 필수 가중치 값과 무관(구조상 불변).")
