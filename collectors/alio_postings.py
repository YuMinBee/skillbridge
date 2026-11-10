"""잡알리오(재정경제부 공공기관 채용정보) 공고 수집 → 시장 분석 실공고 (DATA_MODE=live).

API: POST https://opendata.alio.go.kr/new/v1/recruit/list.do (명세: /new/v2/api-docs?group=recruit)
인증키: .env ALIO_API_KEY (청년 일자리 올인원 서비스에서 발급. data.go.kr 키와 다름)

흐름
1. 공시 시작일 기준 최근 N개월 공고를 1,000건씩 받는다. 원본은 backend/.data/raw/alio/에 남긴다 (배포 시 S3 raw/).
2. 지원자격·우대조건을 '자격요건/우대사항' 섹션 텍스트로 묶어 seed/market/postings_live.jsonl에 쓴다 (S3 curated/).
   직무는 job="public"(공공기관 전 직무), NCS 대분류는 ncs[]에 그대로 둔다.

공고에는 개인정보가 없다(기관 공시). 키는 오류 메시지·파일에 남기지 않는다.
실행: python collectors/alio_postings.py [--months 12]
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from dotenv import dotenv_values  # noqa: E402

URL = "https://opendata.alio.go.kr/new/v1/recruit/list.do"
RAW = ROOT / "backend" / ".data" / "raw" / "alio"
OUT = ROOT / "seed" / "market" / "postings_live.jsonl"
SOURCE = "잡알리오 · 재정경제부 공공기관 채용정보"
DG, CAPITAL = {"대구", "경북"}, {"서울", "경기", "인천"}
PAGE = 1000


class Alio:
    def __init__(self, key: str):
        if not key:
            sys.exit(".env에 ALIO_API_KEY가 없습니다 (opendata.alio.go.kr 채용정보 오픈API 신청)")
        self.key = key

    def list(self, **params) -> dict:
        q = urllib.parse.urlencode({"serviceKey": self.key, "resultType": "json", **params})
        req = urllib.request.Request(f"{URL}?{q}", method="POST", data=b"{}",
                                     headers={"Content-Type": "application/json"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = json.loads(r.read().decode("utf-8"))
                if str(d.get("resultCode")) not in ("200", "0"):
                    raise RuntimeError(f"ALIO 응답 오류 {d.get('resultCode')}: {d.get('resultMsg')}")
                return d
            except Exception as e:  # noqa: BLE001
                msg = str(e).replace(self.key, "***")
                if attempt == 3:
                    raise RuntimeError(f"ALIO 호출 실패: {type(e).__name__} {msg[:200]}") from None
                time.sleep(2 * (attempt + 1))


def _split(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _ymd(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if s and len(s) >= 8 else ""


def region_group(regions: list[str]) -> str:
    if any(r in DG for r in regions):
        return "대경권"
    if any(r in CAPITAL for r in regions):
        return "수도권"
    return "기타"


def to_posting(r: dict) -> dict:
    regions = _split(r.get("workRgnNmLst"))
    pref = "\n".join(x for x in {(r.get("prefCondCn") or "").strip(), (r.get("prefCn") or "").strip()} if x)
    text = "자격요건\n" + (r.get("aplyQlfcCn") or "").strip()
    if pref:
        text += "\n우대사항\n" + pref
    return {
        "id": f"ALIO-{r['recrutPblntSn']}", "source": SOURCE,
        "company": r.get("instNm", ""), "title": (r.get("recrutPbancTtl") or "").strip(),
        "job": "public", "ncs": _split(r.get("ncsCdNmLst")),
        "region": region_group(regions), "regions": regions,
        "hire": _split(r.get("hireTypeNmLst")), "headcount": r.get("recrutNope"),
        "date": _ymd(r.get("pbancBgngYmd", "")), "end": _ymd(r.get("pbancEndYmd", "")),
        "url": r.get("srcUrl") or "", "text": text.replace("\r\n", "\n"),
    }


def collect(months: int) -> list[dict]:
    api = Alio(dotenv_values(ROOT / ".env").get("ALIO_API_KEY", ""))
    today = dt.date.today()
    start = today - dt.timedelta(days=30 * months)
    params = {"pbancBgngYmd": start.isoformat(), "pbancEndYmd": today.isoformat(), "numOfRows": PAGE}
    RAW.mkdir(parents=True, exist_ok=True)
    rows, page, total = [], 1, None
    while total is None or len(rows) < total:
        d = api.list(pageNo=page, **params)
        total = int(d.get("totalCount") or 0)
        got = d.get("result") or []
        (RAW / f"list_{today:%Y%m%d}_p{page:02d}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        rows += got
        print(f"  page {page}: {len(got)}건 (누적 {len(rows)}/{total})")
        if not got:
            break
        page += 1
    seen, out = set(), []
    for r in rows:
        if r.get("recrutPblntSn") in seen:
            continue
        seen.add(r.get("recrutPblntSn"))
        out.append(to_posting(r))
    out.sort(key=lambda p: p["date"])
    OUT.write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in out) + "\n", encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}: {len(out)}건 ({start} ~ {today})")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    collect(ap.parse_args().months)
