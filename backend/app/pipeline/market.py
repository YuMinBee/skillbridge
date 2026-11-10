"""시장 집계: 지역·직무별 스킬 언급률, 급상승 스킬, 근거 공고 문장.

M3에서는 같은 계산을 Athena 쿼리(curated/ 테이블)로 옮긴다. 여기 로직이 기준 구현이다.
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from ..config import DB_PATH, SKILLS_CSV
from ..data import market_postings
from ..skills import get_dict
from . import extract
from .extract import extract_posting

REGIONS = {"dg": "대경권", "all": "전국"}
# ai·cloud = 라벨링한 가상 샘플(민간 AI·클라우드 직무 시연용), public* = 잡알리오 실공고(공공기관 전 직무)
JOBS = {"ai": "AI 엔지니어", "cloud": "클라우드 엔지니어", "public": "공공기관 전 직무", "public_it": "공공기관 정보통신"}
LIVE_JOBS = {"public", "public_it"}


def _job_match(r: dict, job: str) -> bool:
    if job == "public_it":
        return r["job"] == "public" and "정보통신" in r.get("ncs", [])
    return r["job"] == job


def _cache_path(rows: list[dict]) -> Path:
    """사전·추출 규칙·공고가 바뀌면 키가 바뀐다 (1만 건 추출이 1분 가까이 걸려 디스크에 둔다)."""
    h = hashlib.sha1(SKILLS_CSV.read_bytes() + Path(extract.__file__).read_bytes())
    for r in rows:
        h.update(r["id"].encode() + str(len(r["text"])).encode())
    return Path(DB_PATH).parent / f"market_index_{h.hexdigest()[:12]}.json"


@lru_cache(maxsize=1)
def _indexed():
    posts = market_postings()
    cp = _cache_path(posts)
    cache = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else None
    if cache is None:
        cache = {p["id"]: extract_posting(p["text"]) for p in posts}
        cp.parent.mkdir(parents=True, exist_ok=True)
        for old in cp.parent.glob("market_index_*.json"):
            old.unlink(missing_ok=True)
        cp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    rows = [{**p, "skills": {m["skill_id"]: m for m in cache.get(p["id"], [])}} for p in posts]
    months = sorted({r["date"][:7] for r in rows if r.get("date")})
    return rows, months


def _filter(region: str, job: str):
    rows, _ = _indexed()
    sel = [r for r in rows if _job_match(r, job) and (region == "all" or r["region"] == REGIONS[region])]
    months = sorted({r["date"][:7] for r in sel if r.get("date")})
    return sel, months


def source_label(job: str, n: int) -> str:
    if job in LIVE_JOBS:
        return f"잡알리오 실공고 {n:,}건 (재정경제부 공공기관 채용정보, 자격요건·우대조건 문장)"
    return "가상 샘플 공고 (라벨링한 시연용 · 민간 AI·클라우드 직무)"


def _rates(rows) -> dict[str, float]:
    if not rows:
        return {}
    cnt: dict[str, int] = {}
    for r in rows:
        for sid in r["skills"]:
            cnt[sid] = cnt.get(sid, 0) + 1
    return {sid: c / len(rows) * 100 for sid, c in cnt.items()}


def rates(region: str, job: str) -> dict[str, float]:
    """{skill_id: 언급률(%)}"""
    sel, _ = _filter(region, job)
    return _rates(sel)


def rate_for_company(company: dict) -> dict[str, float]:
    region = "dg" if company.get("region") == "대경권" else "all"
    return rates(region, company.get("job", "ai"))


def summary(region: str = "dg", job: str = "ai", top_n: int = 10) -> dict:
    sd = get_dict()
    sel, months = _filter(region, job)
    r_all = _rates(sel)
    top = sorted(r_all.items(), key=lambda x: -x[1])[:top_n]

    recent_m, prev_m = set(months[-6:]), set(months[-12:-6])
    recent = _rates([r for r in sel if r["date"][:7] in recent_m])
    prev = _rates([r for r in sel if r["date"][:7] in prev_m])
    rising = sorted(((sid, recent.get(sid, 0) - prev.get(sid, 0)) for sid in set(recent) | set(prev)),
                    key=lambda x: -x[1])
    rising = [x for x in rising if x[1] > 0][:5]

    evidence = []
    for sid, _ in top[:3]:
        latest = max((r for r in sel if sid in r["skills"]), key=lambda r: r["date"], default=None)
        if latest:
            m = latest["skills"][sid]
            evidence.append({"skill": sd.name(sid), "text": m["evidence"], "section": m["section"],
                             "company": latest["company"], "date": latest["date"],
                             "region": latest["region"], "source": latest["source"], "posting_id": latest["id"]})

    return {
        "region": REGIONS[region], "job": JOBS[job], "n": len(sel),
        "period": f"{months[0]} ~ {months[-1]}" if months else "",
        "top": [{"skill_id": s, "name": sd.name(s), "pct": round(v, 1)} for s, v in top],
        "rising": [{"skill_id": s, "name": sd.name(s), "delta_pp": round(d, 1),
                    "recent_pct": round(recent.get(s, 0), 1), "prev_pct": round(prev.get(s, 0), 1)} for s, d in rising],
        "rising_window": {"recent": f"{months[-6]} ~ {months[-1]}", "prev": f"{months[-12]} ~ {months[-7]}"} if len(months) >= 12 else None,
        "evidence": evidence,
        "source": source_label(job, len(sel)), "live": job in LIVE_JOBS,
    }


def posting_requirement_maps(region: str, job: str) -> list[dict[str, int]]:
    """경로 최적화용: 해당 지역·직무 공고 각각의 요구역량 {skill_id: 2(필수)|1(우대)}"""
    sel, _ = _filter(region, job)
    return [{sid: 2 if m["requirement"] == "required" else 1 for sid, m in r["skills"].items()} for r in sel]


def curated_rows():
    """S3 curated/ 적재용 (Athena 테이블 postings · posting_skills). 같은 추출 결과를 쓰므로 로컬 집계와 숫자가 같아야 한다."""
    rows, _ = _indexed()
    posts = [{"posting_id": r["id"], "source": r.get("source", ""), "job": r["job"], "region": r["region"],
              "month": (r.get("date") or "")[:7], "ncs": r.get("ncs", []), "company": r.get("company", "")} for r in rows]
    skills = [{"posting_id": r["id"], "job": r["job"], "region": r["region"], "month": (r.get("date") or "")[:7],
               "skill_id": sid, "requirement": m["requirement"]} for r in rows for sid, m in r["skills"].items()]
    return posts, skills
