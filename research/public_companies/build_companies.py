"""조사 결과(batch_*.json)를 seed/companies/{ID}.json 으로 변환한다.

- 지원 기준(apply_requirements) = 공고 자격요건(2)·우대(1). 출처 '공고'.
- 실무 기준(requirements)       = 지원 기준 + 기술 블로그·발표에서 확인한 기술(중요도를 몰라 '우대' 1).
- 근거(sources): 스킬마다 원문 인용과 URL. 공고 인용은 공고 문장 중 그 스킬 별칭이 들어간 줄.
"""
import csv, glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
ML = {"naver", "kakaopay", "daangn", "kurly", "hyperconnect", "socar", "ridi", "upstage", "poscodx", "makinarocks", "kakaostyle", "yogiyo", "hanati", "scatterlab", "kakaomobility", "day1"}  # 시장 비교 직무: ML 계열은 ai, 나머지는 cloud(백엔드·인프라)

skills = {r["skill_id"]: r for r in csv.DictReader(open(ROOT / "data/skills.csv", encoding="utf-8-sig"))}


def aliases(sid):
    r = skills[sid]
    al = [r["canonical"]] + [a for col in ("aliases_ko", "aliases_en") for a in r[col].split("|") if a]
    return [a.strip() for a in al if a.strip()]


def find_quote(sid, lines):
    for ln in lines:
        low = ln.lower()
        if any(a.lower() in low for a in aliases(sid) if len(a) >= 2):
            return ln
    return None


def build(c, tid):
    p = c["posting"]
    req_lines = p.get("requirements_quotes", [])
    pref_lines = p.get("preferred_quotes", [])
    explicit = p.get("quotes", {})
    apply = dict(c["apply_skills"])
    sources = {}
    for sid, w in apply.items():
        q = explicit.get(sid) or find_quote(sid, req_lines if w == 2 else pref_lines) or find_quote(sid, req_lines + pref_lines)
        if not q:
            # 공고 본문 줄에서 다시 찾기
            q = find_quote(sid, p.get("posting_text", "").split("\n"))
        sources[sid] = {"from": "공고" if w == 2 else "공고(우대)", "url": p["url"], "quote": (q or "공고 본문 참고").strip()}
    reqs = dict(apply)
    for ws in c["work_sources"]:
        sid = ws["skill_id"]
        reqs.setdefault(sid, 1)
        if sid not in apply or sid not in sources or sources[sid]["from"] != "기술 블로그":
            # 블로그 근거가 있으면 실무 근거로 덮어쓴다(공고 근거는 지원 기준 표시에 남는다)
            if sid not in apply:
                sources[sid] = {"from": ws["from"], "url": ws["url"], "quote": ws["quote"], "date": ws.get("date", "")}
    gap = [s for s in reqs if s not in apply]
    blog_note = "; ".join(c.get("caveats", []))
    return {
        "tenant_id": tid,
        "name": f"{c['company']}(공개 자료 재구성)",
        "desc": f"{c['job_title']} · 실제 공고 + 기술 블로그",
        "region": c.get("region", "수도권"),
        "job": "ai" if c["key"] in ML else "cloud",
        "job_title": c["job_title"],
        "data_note": ("기업이 직접 등록한 기준이 아닙니다. 지원 기준은 실제 채용 공고, 실무 기준은 같은 회사의 기술 블로그·발표에서 "
                      "확인한 기술로 재구성했습니다. 블로그에서 확인한 기술은 중요도를 알 수 없어 '우대'로 두었습니다. "
                      f"공고: {p.get('date_or_status','')}. 주의: {blog_note}. 2026-11-16 확인."),
        "apply_source": "공고",
        "apply_requirements": apply,
        "work_source": "공고 + 기술 블로그",
        "requirements": reqs,
        "sources": sources,
        "excluded": [],
        "posting_text": p.get("posting_text", ""),
        "tracks": [],
        "domain": {"label": c["company"].split("(")[0] + " " + c["job_title"].split(" - ")[0][:20],
                   "keywords": c.get("domain_keywords", [])[:8],
                   "note": "조사에서 뽑은 도메인 단어 (프로젝트 적합도용)"},
        "public_source": {"org": c.get("org_or_team", ""), "caveats": c.get("caveats", []), "posting_url": p["url"]},
        "_gap_only_in_blog": gap,
    }


def main():
    items = []
    for f in sorted(HERE.glob("batch_*.json")):
        items += json.load(open(f, encoding="utf-8"))
    existing = {}
    for f in (ROOT / "seed/companies").glob("*.json"):
        d = json.load(open(f, encoding="utf-8"))
        existing[d["name"]] = d["tenant_id"]
    used = set(existing.values())
    letters = [chr(x) for x in range(ord("I"), ord("Z") + 1)] + [f"Z{i}" for i in range(1, 60)]
    free = iter(l for l in letters if l not in used)
    out = []
    for c in items:
        tid = existing.get(f"{c['company']}(공개 자료 재구성)") or next(free)  # 다시 돌려도 같은 ID
        bad = sorted((set(c["apply_skills"]) | {w["skill_id"] for w in c["work_sources"]}) - set(skills))
        if bad:
            print("SKIP", c["key"], "unknown skill ids:", bad); continue
        d = build(c, tid)
        if not d["_gap_only_in_blog"]:
            print("SKIP", c["key"], "블로그에만 있는 기술이 없음"); continue
        gap = d.pop("_gap_only_in_blog")
        if "--write" in sys.argv:
            json.dump(d, open(ROOT / f"seed/companies/{tid}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        out.append((tid, c["key"], len(d["apply_requirements"]), len(d["requirements"]), gap))
    for r in out:
        print(*r)


if __name__ == "__main__":
    main()
