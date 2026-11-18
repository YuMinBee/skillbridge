"""고용24 공채속보 API(개인 회원 사용 가능) → 민간 기업 IT 직무 공고 (seed/market/gongchae_it.jsonl).

워크넷 채용정보 API(210L01)는 개인 회원이 쓸 수 없다(2026-11-17 재확인: "개인회원은 사용할 수 없는 OPEN-API").
공채속보(210L21 목록 · 210D21 상세)는 된다. 상세에 모집 직무마다 담당업무(jobCont)와 자격요건(sptCertEtc)이 있다.

- 기업 구분이 공기업·공공기관이면 뺀다(공공 쪽은 잡알리오). 민간만.
- 모집 직무 중 IT 직무만 남긴다: 직무명에 IT 단어가 있고 영업·마케팅·사업개발·생산 등 비IT 단어가 없을 것.
- 저장하지 않는 것: 문의처(inqryCont), 로고 이미지.
실행: python collectors/work24_gongchae.py
"""
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

BASE = "https://www.work24.go.kr/cm/openApi/call/wk/"
OUT = ROOT / "seed" / "market" / "gongchae_it.jsonl"
PUBLIC = re.compile(r"공기업|공공기관|공사|공단")
IT_TITLE = re.compile(r"SW|S/W|소프트웨어|\bIT|전산|정보시스템|데이터|AI|인공지능|머신러닝|클라우드|정보\s*보안|보안\s*(?:연구|위협)|백엔드|프론트엔드|프런트엔드|"
                      r"웹\s*개발|앱\s*개발|DevOps|ML|DBA|빌드시스템|모바일플랫폼|게임 개발|업무\s*자동화|Data|Software|엔지니어링_")
NOT_IT = re.compile(r"영업|마케팅|사업\s*개발|사업개발|총무|정산|의전|PR|홍보|생산|품질|자재|CS\b|바잉|AE|IR|공시|화장품|제약|부동산|투자|Trading|"
                    r"전략기획|매체|캠페인|객실|디자인|기획자|첨단보안직|Equipment|인프라엔지니어직")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def get(key: str, path: str, **params) -> ET.Element:
    q = urllib.parse.urlencode({"authKey": key, "returnType": "XML", **params})
    for attempt in range(3):
        try:
            body = urllib.request.urlopen(urllib.request.Request(BASE + path + "?" + q, headers={"User-Agent": "skillbridge-hackathon"}),
                                          timeout=30).read()
            time.sleep(0.1)
            return ET.fromstring(body)
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise RuntimeError(f"{path} 실패: {type(e).__name__}") from None  # 키가 메시지에 섞이지 않게
            time.sleep(1.5)


def main():
    key = (dotenv_values(ROOT / ".env").get("WORK24_KEY_RECRUIT") or "").strip()
    if not key:
        raise SystemExit(".env의 WORK24_KEY_RECRUIT가 비어 있습니다")
    rows, page = [], 1
    while True:
        L = get(key, "callOpenApiSvcInfo210L21.do", callTp="L", startPage=str(page), display="100")
        part = [{c.tag: (c.text or "").strip() for c in it} for it in L.iter("dhsOpenEmpInfo")]
        rows += part
        total = int(L.findtext("total") or 0)
        if not part or len(rows) >= total:
            break
        page += 1
    print(f"공채 {len(rows)}건 (기업구분 공기업·공공기관 제외 전)")
    out, n_detail = [], 0
    for r in rows:
        if PUBLIC.search(r.get("coClcdNm", "")):
            continue
        D = get(key, "callOpenApiSvcInfo210D21.do", callTp="D", empSeqno=r["empSeqno"])
        n_detail += 1
        for i, rec in enumerate(D.iter("empRecrListInfo")):
            f = {c.tag: (c.text or "").strip() for c in rec}
            name, duty, req = f.get("empRecrNm", ""), f.get("jobCont", ""), f.get("sptCertEtc", "")
            if NOT_IT.search(name) or not IT_TITLE.search(name):  # 직무명으로 판단 (본문 단어로 거르면 영업·기획이 섞임)
                continue
            out.append({
                "id": f"GC-{r['empSeqno']}-{i}", "source": "고용24 공채속보 API", "company": r.get("empBusiNm", ""),
                "company_type": r.get("coClcdNm", "") or "기타", "title": f"{r.get('empWantedTitle', '')} · {name}",
                "position": name, "career": f.get("empWantedCareerNm", ""), "region": f.get("workRegionNm", ""),
                "start": r.get("empWantedStdt", ""), "end": r.get("empWantedEndt", ""),
                "url": r.get("empWantedHomepgDetail") or r.get("empWantedHomepg") or None,
                "text": f"담당업무\n{duty}\n자격요건\n{req}".strip(),
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for o in out:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"상세 {n_detail}건 조회 → IT 직무 {len(out)}개 · 신입 포함 {sum(1 for o in out if '신입' in o['career'])}개 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
