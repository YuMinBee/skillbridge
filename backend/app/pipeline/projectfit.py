"""프로젝트 적합도. 현업 청취(docs/INTERVIEWS.md): "프로젝트 경험은 필수인데, 그 경험이 해당 부서에 필요한 경험이었는지가 중요하다."

스킬 보유 여부만 보면 'Docker를 써 봤다'와 'Docker로 서비스를 운영했다'가 같은 점수다. 그래서 이력서를
경험 단위(프로젝트·인턴·연구 한 줄)로 나눠, 경험 하나가 그 부서 실무 기준을 얼마나 증명하는지 잰다.

- 점수는 규칙: 경험 하나 안의 스킬만으로 계산한 실무 준비도 (readiness 공식 그대로)
- 도메인 일치: 경험 문장에 부서 도메인 단어가 있는지 (기업 seed의 domain.keywords, 팀이 정함)
- 맞는 경험이 없으면 그 부서용 미니 프로젝트를 제안한다. '보여줄 것'은 현업 문항 원문(sources)을 쓴다
"""
import re

from ..skills import get_dict
from . import implies
from .extract import judge_status
from .score import readiness, status_of

_EXP = re.compile(r"프로젝트|졸업작품|졸업 작품|해커톤|공모전|대회|인턴|연구|논문|개발|구축|운영|배포|담당|업무|서비스|출시|외주|동아리")
_NOT_EXP = re.compile(r"^\s*\[(보유\s*기술|기술|스킬|자격|자격증|교육|학력|어학)\]")
_CONT = re.compile(r"^(\s+|[·ㄴ→└>])")
VERDICT = {"fit": "이 부서에 맞는 경험", "partial": "일부만 맞음", "far": "부서와 거리가 있음"}


def units(text: str) -> list[str]:
    """경험 단위. 한 줄이 한 경험이고, 들여쓴 줄·하위 기호 줄은 앞 경험에 붙인다."""
    out: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if out and _CONT.match(line) and not line.strip().startswith(("-", "•", "[")):
            out[-1] += " " + line.strip()
        else:
            out.append(line.strip())
    return [u for u in out if _EXP.search(u) and not _NOT_EXP.match(u)]


def _unit_skills(unit: str, status_map: dict[str, dict]) -> dict[str, dict]:
    m: dict[str, dict] = {}
    for sid, v in status_map.items():                       # LLM이 찾은 근거가 이 경험 안에 있으면
        ev = (v.get("evidence") or "").strip()
        if ev and not v.get("implied_by") and (ev in unit or unit in ev):
            m[sid] = {"status": v["status"], "evidence": ev}
    for hit in get_dict().find(unit):                       # 사전 매칭 (규칙)
        m.setdefault(hit["skill_id"], {"status": judge_status(unit), "evidence": unit})
    return implies.expand(m)[0]


def _domain_hits(unit: str, company: dict) -> list[str]:
    return [k for k in (company.get("domain") or {}).get("keywords", []) if k.lower() in unit.lower()]


def score_units(text: str, status_map: dict[str, dict], company: dict, reqs: dict[str, int]) -> list[dict]:
    sd = get_dict()
    rows = []
    for u in units(text):
        um = _unit_skills(u, status_map)
        matched = [s for s in sorted(reqs, key=lambda s: (-reqs[s], s)) if status_of(um, s) != "miss"]
        if not um:
            continue
        rows.append({"text": u if len(u) <= 140 else u[:139] + "…",
                     "fit": readiness(reqs, um),
                     "matched": [{"skill_id": s, "name": sd.name(s), "status": um[s]["status"]} for s in matched],
                     "domain": _domain_hits(u, company)})
    rows.sort(key=lambda r: (-r["fit"], -len(r["domain"])))
    return rows


def _verdict(best: dict | None) -> str:
    if not best or best["fit"] < 25:
        return "far"
    return "fit" if best["fit"] >= 50 and best["domain"] else "partial"


def mini_project(company: dict, reqs: dict[str, int], status_map: dict[str, dict]) -> dict:
    """부서 맞춤 미니 프로젝트: 필수 갭을 중심에 두고, 이미 가진 부서 스킬 하나를 발판으로 쓴다."""
    sd = get_dict()
    soft = {"communication", "english", "technical_writing", "agile", "office", "gen_ai_use"}  # 프로젝트로 보여줄 기술이 아님
    tech = [s for s in sorted(reqs, key=lambda s: (-reqs[s], s)) if s not in soft]
    gap = [s for s in tech if status_of(status_map, s) != "own"]
    have = [s for s in tech if status_of(status_map, s) == "own"]
    skills = (gap[:3] + have[:1]) or list(reqs)[:3]
    src = company.get("sources") or {}
    show = [{"skill": sd.name(s), "what": src[s]["quote"] if s in src else f"{sd.name(s)}를 실제로 쓴 흔적(코드·설정·결과 화면)"}
            for s in skills]
    dom = (company.get("domain") or {}).get("label") or company.get("desc", "")
    return {"title": f"{company.get('job_title', '')} 미니 프로젝트 · {dom}",
            "skills": [sd.name(s) for s in skills], "show": show,
            "note": "결과물은 이력서에 '프로젝트' 한 줄로 쓰고, 위 문항이 보이게 적으세요. 현업은 이 부서에 맞는 경험인지를 봅니다."}


def assess(text: str, status_map: dict[str, dict], company: dict, reqs: dict[str, int]) -> dict:
    rows = score_units(text, status_map, company, reqs)
    best = rows[0] if rows else None
    v = _verdict(best)
    return {"verdict": v, "verdict_label": VERDICT[v], "best_fit": best["fit"] if best else 0,
            "domain_label": (company.get("domain") or {}).get("label"),
            "units": [r for r in rows if r["fit"] > 0 or r["domain"]][:5], "n_units": len(rows),
            "mini_project": mini_project(company, reqs, status_map) if v != "fit" else None,
            "quote": "프로젝트 경험은 필수인데, 그 경험이 해당 부서에 필요한 경험이었는지가 중요하다 (현업 청취)"}


def best_fit(text: str, status_map: dict[str, dict], company: dict, reqs: dict[str, int]) -> int:
    rows = score_units(text, status_map, company, reqs)
    return rows[0]["fit"] if rows else 0
