"""편향 없는 갭 비율: 같은 팀 블로그 원문 전체와 공고 원문을 '같은 추출기'로 뽑아 비교한다.
조사 때 고른 work_sources·apply_skills는 쓰지 않는다 (조사 지시가 '공고에 없는 기술'을 찾게 했으므로 편향됨).

    python eval/gap/fetch_blogs.py <작업폴더>/blogs        # 블로그 원문 받기 (저작권: 레포에 넣지 않는다)
    python eval/gap/gap_measure.py <작업폴더>/blogs llm     # Bedrock: 블로그는 '팀이 실제로 쓰는 기술'만, 공고는 사전∪LLM
    python eval/gap/gap_measure.py <작업폴더>/blogs rule    # 참고: 사전 매칭만 (사이드바·광고까지 잡혀 과대)

2026-11-16 결과(result_llm.json): 10개 회사 · 블로그 기술 68개 중 공고에 없음 31개 = 45.6% (95% 구간 31.9–60.0%).
애매한 3개(JNI→Java, JVM→Java·가상화)를 빼면 43%. 403으로 막힌 4곳(우아한형제들·당근·직방·마이리얼트립)은 제외(우회하지 않음).
"""
import glob, json, random, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # 레포 루트
sys.path.insert(0, str(REPO / "backend"))
from app.pipeline import extract  # noqa: E402
from app.pipeline.family import SOFT  # noqa: E402
from app.pipeline.implies import ancestors  # noqa: E402

BL = Path(sys.argv[1]); MODE = sys.argv[2]
idx = json.load(open(BL / "index.json", encoding="utf-8"))
best = {}
for f in sorted(glob.glob(str(REPO / "research/public_companies/batch_*.json"))):
    for c in json.load(open(f, encoding="utf-8")): best[c["key"]] = c


sys.path.insert(0, str(Path(__file__).parent))
EVID = {}


def post_skills(text: str) -> set[str]:
    s = {m["skill_id"] for m in extract.extract_posting(text)}
    if MODE == "llm":  # 공고 쪽은 사전 ∪ LLM으로 넉넉히 → 갭 비율은 보수적으로(작게) 나온다
        s |= {m["skill_id"] for m in extract.extract_posting_llm(text)}
    return s - SOFT


def blog_skills(text: str, k: str) -> set[str]:
    if MODE == "rule":
        return {m["skill_id"] for m in extract.extract_posting(text)} - SOFT
    from blog_llm import blog_skills as bl
    items = bl(text, BL.parent / f"blog_llm_{k}.json")
    for m in items: EVID.setdefault(k, {}).setdefault(m["skill_id"], m["evidence"])
    return {m["skill_id"] for m in items} - SOFT


rows = []
for k, docs in idx.items():
    docs = [d for d in docs if d["quote_hit"] > 0 and d["chars"] > 500]  # 본문을 제대로 받은 글만
    if not docs: continue
    c = best[k]; p = c["posting"]
    post = "\n".join([p.get("posting_text", "")] + p.get("requirements_quotes", []) + p.get("preferred_quotes", []))
    blog = "\n".join((BL / d["file"]).read_text(encoding="utf-8") for d in docs)
    P, W = post_skills(post), blog_skills(blog, k)
    # 상하위 보정: 공고의 상위 스킬이 블로그 하위 스킬을 덮거나 그 반대면 '공고에 있음'으로 본다
    Pc = P | {a for s in P for a in ancestors(s)}
    missing = {s for s in W if s not in Pc and not (set(ancestors(s)) & P)}
    rows.append({"key": k, "company": c["company"], "match": c["match"], "posting": sorted(P), "blog": sorted(W),
                 "in_both": sorted(W - missing), "blog_only": sorted(missing), "posting_only": sorted(P - W),
                 "evidence": {s: EVID.get(k, {}).get(s, "") for s in sorted(missing)}})

tot_w = sum(len(r["blog"]) for r in rows); tot_m = sum(len(r["blog_only"]) for r in rows)
ratio = tot_m / tot_w
# 회사 단위 부트스트랩 (같은 회사 기술끼리는 독립이 아니므로 회사로 묶어 재표집)
random.seed(0); bs = []
for _ in range(5000):
    s = [random.choice(rows) for _ in rows]
    w = sum(len(r["blog"]) for r in s)
    if w: bs.append(sum(len(r["blog_only"]) for r in s) / w)
bs.sort(); lo, hi = bs[int(.025 * len(bs))], bs[int(.975 * len(bs))]
per = [len(r["blog_only"]) / len(r["blog"]) for r in rows if r["blog"]]
out = {"mode": MODE, "companies": len(rows), "blog_skills": tot_w, "blog_only": tot_m, "ratio": ratio,
       "ci95": [lo, hi], "per_company_median": sorted(per)[len(per) // 2], "rows": rows}
json.dump(out, open(BL.parent / f"gap_{MODE}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for r in rows:
    print(f"{r['company'][:14]:<14} 블로그 {len(r['blog']):>2} 공고에없음 {len(r['blog_only']):>2}  예: {', '.join(r['blog_only'][:6])}")
print(f"[{MODE}] {len(rows)}곳 · 블로그 기술 {tot_w}개 중 공고에 없음 {tot_m}개 = {ratio:.1%} (95% CI {lo:.1%}–{hi:.1%}), 회사별 중앙값 {out['per_company_median']:.1%}")
