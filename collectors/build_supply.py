"""훈련과정 원본에서 스킬 × 지역 '교육 공급'을 집계한다. API를 다시 부르지 않는다.

입력
- region_*.json : 대구·경북·서울·경기·인천의 개강 예정 '전체' 회차 (work24_courses.py --region-scan)
- list_*.json   : 스킬 검색어별 회차 (원격 과정 수 집계용, 검색어당 최대 100건이라 하한값)

공급 = 개강 예정 대면 회차의 정원(yardMan) 합계. 원격 과정은 정원이 500·1000 같은 명목값이 많아
지역 공급에서 빼고 '원격 회차 수'로 따로 센다 (과정명·기관명에 원격/온라인이 있거나 정원 300 이상).
지역 비교는 각 지역 '전체 훈련 정원' 대비 비중으로 한다 → 인구 같은 외부 데이터 없이 공정한 비교.

실행: python collectors/build_supply.py  → seed/market/supply_live.json
"""
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.skills import get_dict  # noqa: E402
from work24_courses import RAW, SKIP_CATEGORIES  # noqa: E402

OUT = ROOT / "seed" / "market" / "supply_live.json"
ONLINE_SEATS = 300
GROUPS = {"대경권": ("대구", "경북"), "수도권": ("서울", "경기", "인천")}
TECH = {"언어", "데이터", "머신러닝", "딥러닝", "컴퓨터비전", "자연어처리", "생성형AI", "AWS", "클라우드", "컨테이너",
        "IaC", "운영체제", "인프라", "DevOps", "모니터링", "MLOps", "데이터엔지니어링", "DB", "백엔드", "프론트엔드",
        "아키텍처", "보안", "로보틱스", "임베디드", "음성"}
# IT 자격증 과정(정보처리·정보보안·네트워크·데이터)은 IT 교육으로 센다. 사무 OA·컴활·'생성형 AI 활용' 사무 과정은 제외.
TECH_IDS = {"cert_info_processing", "cert_security", "cert_network", "cert_data"}


def _latest(pattern):
    f = sorted(glob.glob(str(RAW / pattern)))
    if not f:
        raise SystemExit(f"원본 없음: {pattern} (collectors/work24_courses.py 먼저)")
    return Path(f[-1])


def _online(r) -> bool:
    return any(w in r.get("title", "") + r.get("subTitle", "") for w in ("원격", "온라인")) or \
        int(float(r.get("yardMan") or 0)) >= ONLINE_SEATS


def main():
    sd = get_dict()

    def skills_of(title):
        return {m["skill_id"] for m in sd.find(title) if sd.skills[m["skill_id"]]["category"] not in SKIP_CATEGORIES}

    reg_f = _latest("region_*.json")
    reg = json.loads(reg_f.read_text(encoding="utf-8"))
    by_skill = defaultdict(lambda: {g: {"seats": 0, "rounds": 0, "example": ""} for g in GROUPS})
    totals = {g: {"seats": 0, "rounds": 0, "tech_seats": 0, "tech_rounds": 0, "online_excluded": 0} for g in GROUPS}
    for g, areas in GROUPS.items():
        seen = set()
        for a in areas:
            for r in reg["areas"][a]["rows"]:
                k = (r.get("trprId"), r.get("trprDegr"))
                if k in seen:
                    continue
                seen.add(k)
                if _online(r):
                    totals[g]["online_excluded"] += 1
                    continue
                seats = int(float(r.get("yardMan") or 0))
                totals[g]["seats"] += seats
                totals[g]["rounds"] += 1
                sk = skills_of(r.get("title", ""))
                if any(sd.skills[s]["category"] in TECH or s in TECH_IDS for s in sk):
                    totals[g]["tech_seats"] += seats
                    totals[g]["tech_rounds"] += 1
                for s in sk:
                    b = by_skill[s][g]
                    b["seats"] += seats
                    b["rounds"] += 1
                    b["example"] = b["example"] or f"{r.get('title', '')} · {r.get('subTitle', '')}"

    online = defaultdict(set)
    for kw in json.loads(_latest("list_*.json").read_text(encoding="utf-8")):
        for r in kw["rows"]:
            if _online(r):
                for s in skills_of(r.get("title", "")):
                    online[s].add((r.get("trprId"), r.get("trprDegr")))

    skills = {}
    for s in sorted(set(by_skill) | set(online)):
        skills[s] = {**{g: by_skill[s][g] for g in GROUPS}, "online_rounds_min": len(online.get(s, ()))}
    for g in GROUPS:
        t = totals[g]
        t["tech_share_pct"] = round(t["tech_seats"] / t["seats"] * 100, 2) if t["seats"] else 0
    out = {"_note": __doc__.strip().splitlines()[0], "window": reg["window"], "region_file": reg_f.name,
           "groups": {g: list(a) for g, a in GROUPS.items()}, "totals": totals, "skills": skills}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for g, t in totals.items():
        print(f"{g}: 대면 {t['rounds']}회차 · 정원 {t['seats']:,} · 그중 IT·AI {t['tech_seats']:,} ({t['tech_share_pct']}%) · 원격 제외 {t['online_excluded']}")
    print(f"스킬 {len(skills)}개 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
