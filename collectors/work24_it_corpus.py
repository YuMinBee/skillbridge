"""고용24 훈련과정 중 NCS 정보기술(2001) 전체 → RAG 코퍼스 (seed/corpus/courses_it.jsonl).

기존 live_courses.json은 '과정명에 사전 단어가 있는 것, 스킬별 6개'만 골라서 키워드 검색에 유리하게 치우쳐 있다.
RAG를 공정하게 재려면 단어로 거르지 않은 전체가 필요하다 → NCS 분류로만 받는다.

- 목록 API(310L01)만 쓴다(과정 수천 개라 상세 API는 부르지 않음 → 훈련시간 없음, 기간·비용·취업률은 있음).
- 같은 과정(trprId)의 여러 회차는 앞으로 가장 빨리 개강하는 회차 하나만 남긴다. 오늘 이후 개강만.
- 저장하지 않는 것: 기관 전화번호(telNo).
실행: python collectors/work24_it_corpus.py [--months 4]
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import dotenv_values  # noqa: E402
from work24_courses import Work24, _rows, region_of  # noqa: E402

OUT = ROOT / "seed" / "corpus" / "courses_it.jsonl"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def collect(months: int) -> list[dict]:
    key = (dotenv_values(ROOT / ".env").get("WORK24_KEY_TRAINING") or "").strip()
    if not key:
        raise SystemExit(".env의 WORK24_KEY_TRAINING이 비어 있습니다")
    api = Work24(key, pause=0.1)
    today = dt.date.today()
    st, en = today.strftime("%Y%m%d"), (today + dt.timedelta(days=30 * months)).strftime("%Y%m%d")
    found: dict[str, dict] = {}
    page, total = 1, None
    while True:
        root = api.get("callOpenApiSvcInfo310L01.do", outType="1", pageNum=str(page), pageSize="100", srchTraStDt=st,
                       srchTraEndDt=en, sort="ASC", sortCol="TRNG_BGDE", srchNcs1="20", srchNcs2="2001")
        total = total or int(root.findtext("scn_cnt") or 0)
        rows = _rows(root)
        for r in rows:
            if r.get("traStartDate", "") < today.isoformat():
                continue
            cur = found.get(r.get("trprId"))
            if cur is None or r.get("traStartDate", "") < cur.get("traStartDate", ""):
                found[r["trprId"]] = r
        if page % 20 == 0:
            print(f"  {page * 100:,}/{total:,} · 과정 {len(found):,}")
        if not rows or page * 100 >= total:
            break
        page += 1
    print(f"목록 {total:,}회차 → 과정 {len(found):,}개 · API {api.calls}회")
    out = []
    for r in found.values():
        title = r.get("title", "").strip()
        out.append({
            "doc_id": f"W24-{r['trprId']}-{r.get('trprDegr', '')}",
            "kind": "course",
            "title": title,
            "text": " · ".join(x for x in [title, r.get("subTitle", ""), r.get("trainTarget", "")] if x),
            "source": "고용24 국민내일배움카드 훈련과정 API",
            "url": r.get("titleLink") or None,
            "collected_at": today.isoformat(),
            "meta": {"provider": r.get("subTitle", ""), "ncs": r.get("ncsCd", ""), "start": r.get("traStartDate", ""),
                     "end": r.get("traEndDate", ""), "region": region_of(r.get("address", ""), r.get("subTitle", ""), title),
                     "target": r.get("trainTarget", ""), "cost": r.get("realMan", ""),
                     "employ_rate_3m": r.get("eiEmplRate3", ""), "satisfaction": r.get("stdgScor", "")},
        })
    out.sort(key=lambda d: d["doc_id"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=4)
    docs = collect(ap.parse_args().months)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"저장: {OUT.relative_to(ROOT)} ({len(docs):,}개)")


if __name__ == "__main__":
    main()
