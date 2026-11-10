"""잡알리오 실공고 변환 · 디지털 역량 사전 · 공공기관 분석 API."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "collectors"))

from app.skills import get_dict  # noqa: E402


def _ids(text):
    return {m["skill_id"] for m in get_dict().find(text)}


def test_alio_row_to_posting():
    import alio_postings as a
    row = {"recrutPblntSn": 1, "instNm": "가상공단", "recrutPbancTtl": " 2026 채용 ", "ncsCdNmLst": "정보통신,경영.회계.사무",
           "workRgnNmLst": "대구,서울", "hireTypeNmLst": "정규직", "recrutNope": 2, "pbancBgngYmd": "20261101",
           "pbancEndYmd": "20261110", "srcUrl": "x", "aplyQlfcCn": "정보처리기사 소지자\r\n", "prefCondCn": "SQLD 우대", "prefCn": "SQLD 우대"}
    p = a.to_posting(row)
    assert p["id"] == "ALIO-1" and p["job"] == "public" and p["region"] == "대경권"
    assert p["ncs"] == ["정보통신", "경영.회계.사무"] and p["date"] == "2026-11-01"
    assert p["text"].count("SQLD 우대") == 1 and "\r" not in p["text"]
    from app.pipeline.extract import extract_posting
    req = {m["skill_id"]: m["requirement"] for m in extract_posting(p["text"])}
    assert req == {"cert_info_processing": "required", "cert_data": "preferred"}


def test_region_group():
    import alio_postings as a
    assert a.region_group(["경북"]) == "대경권"
    assert a.region_group(["인천"]) == "수도권"
    assert a.region_group(["제주"]) == "기타"


def test_digital_aliases_avoid_false_positives():
    assert "r_lang" not in _ids("R&D 기획 경력자")
    assert "r_lang" in _ids("R, SAS 등 통계 도구")
    assert _ids("OA설비 유지보수") == set()            # 'OA' 단독은 사전에 없다
    assert _ids("생성형 AI 서비스 기획 및 개발") == set()  # 개발 직무 문장은 '활용'이 아니다
    assert "gen_ai_use" in _ids("챗GPT를 활용한 엑셀실무")
    assert "cert_computer" in _ids("컴퓨터활용능력 2급 이상")
    assert "cert_data" in _ids("ADsP, SQLD 소지자")


def test_digital_api_shape(client):
    r = client.get("/api/digital?region=dg")
    assert r.status_code == 200
    d = r.json()
    if not d["available"]:  # 실공고 파일이 없는 환경(샘플 모드)
        return
    o = d["overall"]
    assert 0 <= o["digital"] <= 100 and set(o["groups"]) == {"office", "it", "data", "ai"}
    assert all(f["n"] >= d["min_field"] for f in d["by_field"])
    assert client.get("/api/digital?region=xx").status_code == 400


def test_market_public_jobs(client):
    for job in ("public", "public_it"):
        r = client.get(f"/api/market?region=all&job={job}")
        assert r.status_code == 200
    assert client.get("/api/market?region=all&job=nope").status_code == 400
