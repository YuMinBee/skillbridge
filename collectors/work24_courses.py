"""고용24 국민내일배움카드 훈련과정 수집 → 학습경로 카탈로그 (DATA_MODE=live).

흐름
1. 스킬 사전의 기술 이름(표준명 + 대표 한국어 별칭)으로 과정명을 검색한다 (목록 API 310L01).
2. 과정명·NCS 분류명에서 사전 매칭으로 스킬을 붙이고, 스킬이 하나도 없으면 버린다.
3. 스킬마다 최대 PER_SKILL개만 남긴 뒤(대경권 → 원격(전국) → 그 외, 개강 빠른 순) 상세 API(310L02)로 총 훈련시간을 받는다.
4. 원본 응답은 backend/.data/raw/work24/에 남기고(배포 시 S3 raw/), 정제본은 seed/courses/live_courses.json(S3 curated/)에 쓴다.

저장하지 않는 것: 훈련기관 담당자 이름·이메일·전화 (상세 응답에 있음).
실행: python collectors/work24_courses.py [--months 4] [--per-skill 6]
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import dotenv_values  # noqa: E402

from app.skills import get_dict  # noqa: E402

BASE = "https://www.work24.go.kr/cm/openApi/call/hr/"
UA = {"User-Agent": "skillbridge-hackathon/0.1 (team kosa06)"}
RAW = ROOT / "backend" / ".data" / "raw" / "work24"
OUT = ROOT / "seed" / "courses" / "live_courses.json"
SKIP_CATEGORIES = {"협업", "도구", "연구", "도메인"}  # 과정명 검색으로 의미가 없는 범주
CAPITAL = ("서울", "경기", "인천")
DAEGYEONG = ("대구", "경북", "경상북도")
LEVEL_BASIC = re.compile(r"기초|입문|초급|BASIC|Basic|basic|첫걸음|시작|이해")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class Work24:
    def __init__(self, key: str, pause: float = 0.15):
        self.key, self.pause, self.calls = key, pause, 0

    def get(self, endpoint: str, **params) -> ET.Element:
        q = urllib.parse.urlencode({"authKey": self.key, "returnType": "XML", **params})
        for attempt in range(3):
            try:
                req = urllib.request.Request(BASE + endpoint + "?" + q, headers=UA)
                body = urllib.request.urlopen(req, timeout=30).read()
                self.calls += 1
                time.sleep(self.pause)
                return ET.fromstring(body)
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    raise RuntimeError(f"{endpoint} 실패: {type(e).__name__}") from None  # 키가 메시지에 섞이지 않게
                time.sleep(1.5 * (attempt + 1))


def _rows(root: ET.Element, tag="scn_list") -> list[dict]:
    return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter(tag)]


def _children(root: ET.Element, tag: str) -> list:
    el = root.find(tag)
    return list(el) if el is not None else []


def keywords() -> list[tuple[str, str]]:
    sd = get_dict()
    out = []
    for sid, s in sd.skills.items():
        if s["category"] in SKIP_CATEGORIES:
            continue
        names = [s["name"]] + [a for a in s.get("aliases", []) if re.search(r"[가-힣]", a)][:1]
        for n in dict.fromkeys(names):
            if len(n) >= 2:
                out.append((sid, n))
    return out


def region_of(address: str, provider: str, title: str, method_cd: str = "") -> str:
    # 훈련방법 코드: M2005 = 원격 (2026-11-09 수집분에서 기관명 '원격'과 일치 확인), M1001 = 집체
    online = method_cd == "M2005" or "원격" in provider or "원격" in title or "온라인" in title
    if online:
        return "전국"
    if address.startswith(DAEGYEONG):
        return "대경권"
    if address.startswith(CAPITAL):
        return "수도권"
    return "기타"


def collect(months: int, per_skill: int, page_size: int = 100) -> dict:
    env = dotenv_values(ROOT / ".env")
    key = (env.get("WORK24_KEY_TRAINING") or "").strip()
    if not key:
        raise SystemExit(".env의 WORK24_KEY_TRAINING이 비어 있습니다")
    api = Work24(key)
    sd = get_dict()
    RAW.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    st, en = today.strftime("%Y%m%d"), (today + dt.timedelta(days=30 * months)).strftime("%Y%m%d")

    found: dict[str, dict] = {}  # trprId → 과정 (가장 빠른 회차)
    raw_list = []
    kws = keywords()
    for i, (sid, kw) in enumerate(kws, 1):
        root = api.get("callOpenApiSvcInfo310L01.do", outType="1", pageNum="1", pageSize=str(page_size),
                       srchTraStDt=st, srchTraEndDt=en, sort="ASC", sortCol="TRNG_BGDE", srchTraProcessNm=kw)
        rows = _rows(root)
        raw_list.append({"keyword": kw, "total": root.findtext("scn_cnt"), "rows": rows})
        for r in rows:
            cur = found.get(r.get("trprId"))
            if cur is None or r.get("traStartDate", "") < cur.get("traStartDate", ""):
                found[r["trprId"]] = r
        if i % 25 == 0:
            print(f"  검색 {i}/{len(kws)} · 누적 과정 {len(found)}")
    (RAW / f"list_{today:%Y%m%d}.json").write_text(json.dumps(raw_list, ensure_ascii=False), encoding="utf-8")

    # 과정명에서 스킬 매칭 (검색어로 걸렸어도 과정명에 스킬이 없으면 버림)
    cands = []
    for r in found.values():
        skills = list(dict.fromkeys(m["skill_id"] for m in sd.find(r.get("title", ""))
                                    if sd.skills[m["skill_id"]]["category"] not in SKIP_CATEGORIES))
        if not skills:
            continue
        reg = region_of(r.get("address", ""), r.get("subTitle", ""), r.get("title", ""))
        cands.append({**r, "_skills": skills, "_region": reg})

    rank = {"대경권": 0, "전국": 1, "수도권": 2, "기타": 3}
    keep: dict[str, dict] = {}
    for sid in {s for c in cands for s in c["_skills"]}:
        pool = sorted((c for c in cands if sid in c["_skills"]),
                      key=lambda c: (rank[c["_region"]], c.get("traStartDate", ""), c["trprId"]))
        for c in pool[:per_skill]:
            keep[c["trprId"]] = c
    print(f"과정명 스킬 매칭 {len(cands)}건 → 스킬별 상위 {per_skill}개 = {len(keep)}건, 상세 조회")

    courses, raw_detail = [], []
    for c in keep.values():
        try:
            d = api.get("callOpenApiSvcInfo310L02.do", outType="2", srchTrprId=c["trprId"],
                        srchTrprDegr=c["trprDegr"], srchTorgId=c.get("trainstCstId", ""))
        except RuntimeError as e:
            print("  상세 실패:", c["trprId"], e)
            continue
        base = {x.tag: (x.text or "").strip() for x in _children(d, "inst_base_info")}
        det = {x.tag: (x.text or "").strip() for x in _children(d, "inst_detail_info")}
        safe = {k: v for k, v in base.items() if not k.startswith("trprChap")}  # 담당자 정보 제외
        raw_detail.append({"trprId": c["trprId"], "base": safe, "detail": det})
        hours = int(float(det.get("totTraingTime") or base.get("trtm") or 0))
        if hours <= 0:
            continue
        title = c["title"]
        skills = list(dict.fromkeys(c["_skills"] + [m["skill_id"] for m in sd.find(base.get("ncsNm", ""))
                                                    if sd.skills[m["skill_id"]]["category"] not in SKIP_CATEGORIES]))
        courses.append({
            "id": f"W24-{c['trprId']}-{c['trprDegr']}",
            "title": title,
            "provider": c.get("subTitle", ""),
            "hours": hours,
            "skills": skills,
            "level": "기초" if LEVEL_BASIC.search(title) else "실무",
            "region": region_of(c.get("address", ""), c.get("subTitle", ""), title, base.get("traingMthCd", "")),
            "address": c.get("address", ""),
            "start": c.get("traStartDate", ""),
            "end": c.get("traEndDate", ""),
            "cost": int(c.get("realMan") or c.get("courseMan") or 0),
            "ncs": {"code": c.get("ncsCd", ""), "name": base.get("ncsNm", "")},
            "target": c.get("trainTarget", ""),
            "satisfaction": c.get("stdgScor", ""),
            "link": c.get("titleLink", ""),
            "source": "고용24 국민내일배움카드 훈련과정 API",
        })
    (RAW / f"detail_{today:%Y%m%d}.json").write_text(json.dumps(raw_detail, ensure_ascii=False), encoding="utf-8")

    courses.sort(key=lambda x: x["id"])
    out = {"_note": f"고용24 OPEN-API로 {today:%Y-%m-%d} 수집. 개강 {st}~{en} 과정 중 과정명에 사전 스킬이 있는 것만, "
                    f"스킬별 최대 {per_skill}개. 원격 과정은 지역 '전국'.",
           "collected_at": today.isoformat(), "api_calls": api.calls, "courses": courses}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    by_region = {r: sum(1 for c in courses if c["region"] == r) for r in rank}
    print(f"완료: {len(courses)}개 과정 → {OUT.relative_to(ROOT)} · API 호출 {api.calls}회 · 지역 {by_region}")
    return out


AREAS = {"대구": "27", "경북": "47", "서울": "11", "경기": "41", "인천": "28"}


def region_scan(months: int, page_size: int = 100) -> Path:
    """검색어 없이 지역별 '모든' 개강 예정 회차를 받는다 (공급 집계용, 분야 무관)."""
    key = (dotenv_values(ROOT / ".env").get("WORK24_KEY_TRAINING") or "").strip()
    api = Work24(key)
    today = dt.date.today()
    st, en = today.strftime("%Y%m%d"), (today + dt.timedelta(days=30 * months)).strftime("%Y%m%d")
    out = {}
    for name, code in AREAS.items():
        rows, page = [], 1
        while True:
            root = api.get("callOpenApiSvcInfo310L01.do", outType="1", pageNum=str(page), pageSize=str(page_size),
                           srchTraStDt=st, srchTraEndDt=en, sort="ASC", sortCol="TRNG_BGDE", srchTraArea1=code)
            got = _rows(root)
            rows += got
            total = int(root.findtext("scn_cnt") or 0)
            if not got or len(rows) >= total:
                break
            page += 1
        out[name] = {"total": total, "rows": rows}
        print(f"  {name}: {len(rows)}/{total}")
    f = RAW / f"region_{today:%Y%m%d}.json"
    RAW.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"window": [st, en], "areas": out}, ensure_ascii=False), encoding="utf-8")
    print(f"지역 전수 수집 → {f.name} · API 호출 {api.calls}회")
    return f


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=4)
    ap.add_argument("--per-skill", type=int, default=6)
    ap.add_argument("--region-scan", action="store_true", help="지역별 전체 회차 수집 (공급 집계용)")
    a = ap.parse_args()
    if a.region_scan:
        region_scan(a.months)
    else:
        collect(a.months, a.per_skill)
