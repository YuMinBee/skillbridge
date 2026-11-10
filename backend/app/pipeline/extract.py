"""스킬 언급 추출.

BEDROCK_MOCK=1 (현재): 별칭 사전 정확 매칭 + 규칙(섹션 헤더, 근거 표현)으로 추출한다.
BEDROCK_MOCK=0: Bedrock 구조화 출력(extract_*_llm)으로 언급을 뽑고, 사전 매칭 실패분은
임베딩 top-k 후보 중에서 LLM이 고른다. 출력 형식은 이 모듈과 동일하게 유지한다.
"""
import re

from ..skills import get_dict, sentences

# ── 공고 ──────────────────────────────────────────────
_SECTION_HEADERS = [
    ("duty", re.compile(r"^\W*(담당\s*업무|주요\s*업무|업무\s*내용)")),
    ("required", re.compile(r"^\W*(자격\s*요건|필수\s*요건|지원\s*자격|필수\s*역량)")),
    ("preferred", re.compile(r"^\W*(우대\s*사항|우대\s*조건|우대\s*역량)")),
]
SECTION_LABEL = {"duty": "담당업무", "required": "자격요건", "preferred": "우대사항"}


def split_sections(text: str) -> list[tuple[str, str]]:
    """[(section, line)] — 헤더 줄 자체는 제외. 헤더 전 줄은 duty로 본다."""
    cur, out = "duty", []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        hit = next((sec for sec, pat in _SECTION_HEADERS if pat.match(s) and len(s) <= 12), None)
        if hit:
            cur = hit
            continue
        out.append((cur, s))
    return out


def extract_posting(text: str) -> list[dict]:
    """공고 → [{skill_id, mention, section, requirement, evidence}] (스킬당 1건, 필수 우선)"""
    sd = get_dict()
    best: dict[str, dict] = {}
    for section, line in split_sections(text):
        req = "preferred" if section == "preferred" else "required"
        for m in sd.find(line):
            cur = best.get(m["skill_id"])
            if cur is None or (cur["requirement"] == "preferred" and req == "required"):
                best[m["skill_id"]] = {"skill_id": m["skill_id"], "mention": m["mention"],
                                       "section": SECTION_LABEL[section], "requirement": req,
                                       "evidence": line.lstrip("-•· ").strip()}
    return list(best.values())


def posting_requirements(text: str) -> dict[str, int]:
    """공고 문구만으로 만든 요구역량 {skill_id: 2(필수)|1(우대)} — '공고만 본 추천' 기준선."""
    return {m["skill_id"]: 2 if m["requirement"] == "required" else 1 for m in extract_posting(text)}


# ── 이력서 ────────────────────────────────────────────
# 약한 근거 표현이 있으면 '부분'이 우선한다 (예: "프로젝트에서 짧게 실습").
_PART = re.compile(r"수업|수강|강의|교육|과제|실습|스터디|튜토리얼|짧게|일부|PoC|준비|기초|입문|독학")
_OWN = re.compile(r"개발|구축|구현|운영|배포|담당|진행|관리|실무|튜닝|분석하|작성|설계|도입|개선|자동화하")
RANK = {"own": 3, "part": 2, "verify": 1, "miss": 0}
STATUS_LABEL = {"own": "보유", "part": "부분", "verify": "검증 필요", "miss": "없음"}


def judge_status(sentence: str) -> str:
    if _PART.search(sentence):
        return "part"
    if _OWN.search(sentence):
        return "own"
    return "verify"


def extract_resume(text: str) -> dict[str, dict]:
    """이력서 → {skill_id: {status, evidence, mention}} (스킬별 가장 강한 근거)"""
    sd = get_dict()
    out: dict[str, dict] = {}
    for sent in sentences(text):
        found = sd.find(sent)
        if not found:
            continue
        st = judge_status(sent)
        for m in found:
            cur = out.get(m["skill_id"])
            if cur is None or RANK[st] > RANK[cur["status"]]:
                out[m["skill_id"]] = {"status": st, "evidence": sent.lstrip("-•· ").strip(), "mention": m["mention"]}
    return out


# ── Bedrock 구조화 추출 (BEDROCK_MOCK=0) ───────────────
_RESUME_SYS = """너는 이력서에서 기술 역량 언급을 빠짐없이 추출한다.
- 기술만 뽑는다: 프로그래밍 언어, 프레임워크·라이브러리, 도구, 클라우드 서비스, 데이터베이스, 기술 분야(예: 컴퓨터 비전, MLOps), 기술 자격증.
  학교·회사·직무명·소프트스킬은 뽑지 않는다.
- mention: 이력서에 쓰인 표현 그대로 (예: "파이토치", "k8s"). 한 문장에 기술이 여러 개면 각각 따로 뽑는다.
- standard_name: 그 기술의 일반적인 표준 이름(보통 영문). 예: 쿠베→Kubernetes, 깃헙 액션→GitHub Actions, 객체 인식→Object Detection.
- evidence: 그 언급이 나온 이력서 문장을 한 글자도 바꾸지 말고 그대로 복사한다.
- status (그 문장만 근거로 판정):
  own = 본인이 그 기술로 직접 무언가를 개발·구현·구축·운영·관리한 근거가 있음.
        실무뿐 아니라 연구실 실험·논문 재현, 졸업작품, 개인·팀 프로젝트에서 직접 수행한 것도 own이다.
  part = 수업·수강·교육과정·실습·스터디·튜토리얼, 또는 '짧게·일부·기초·PoC'처럼 범위가 제한된 경험
  verify = 기술명만 나열되어 있고 실제로 사용한 근거가 없음 (예: [보유기술] 목록)
- 같은 기술이 여러 문장에 나오면 문장마다 따로 뽑는다."""

_RESUME_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "mention": {"type": "string"},
            "standard_name": {"type": "string"},
            "evidence": {"type": "string"},
            "status": {"type": "string", "enum": ["own", "part", "verify"]},
        },
        "required": ["mention", "evidence", "status"]}}},
    "required": ["items"],
}

_POSTING_SYS = """너는 채용공고에서 지원자에게 요구하는 기술 역량을 빠짐없이 추출한다.
- 기술만 뽑는다: 프로그래밍 언어, 프레임워크·라이브러리, 도구, 클라우드 서비스, 데이터베이스, 기술 분야, 기술 자격증.
  학력·연차·소프트스킬·복지는 뽑지 않는다.
- mention: 공고에 쓰인 표현 그대로. 한 줄에 여러 개면 각각 따로.
- standard_name: 그 기술의 일반적인 표준 이름(보통 영문). 예: 쿠베→Kubernetes, 깃헙 액션→GitHub Actions, 객체 인식→Object Detection.
- section: 그 줄이 속한 섹션. duty=담당/주요업무, required=자격/필수요건, preferred=우대사항.
- evidence: 그 줄을 그대로 복사한다."""

_POSTING_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "mention": {"type": "string"},
            "standard_name": {"type": "string"},
            "section": {"type": "string", "enum": ["duty", "required", "preferred"]},
            "evidence": {"type": "string"},
        },
        "required": ["mention", "section", "evidence"]}}},
    "required": ["items"],
}

_WS = re.compile(r"\s+")


def _locate(evidence: str, mention: str, text: str) -> str | None:
    """LLM이 준 근거 문장이 원문에 실제로 있는지 확인한다. 없으면 언급이 들어 있는 원문 문장으로 대체, 그것도 없으면 None."""
    norm = lambda s: _WS.sub(" ", s).strip()  # noqa: E731
    ev = norm(evidence).lstrip("-•· ")
    for sent in sentences(text):
        if ev and ev in norm(sent):
            return sent.lstrip("-•· ").strip()
    for sent in sentences(text):
        if mention and mention.lower() in sent.lower():
            return sent.lstrip("-•· ").strip()
    return None


def extract_resume_llm(text: str, log=None, use_embedding=True, use_llm=True,
                       safety_net=True) -> tuple[dict[str, dict], dict]:
    """→ ({skill_id: {status, evidence, mention, how}}, 통계). 스위치는 평가(eval/run_eval.py) ablation용."""
    from ..adapters import bedrock
    from .normalize import normalize

    out = bedrock.converse_tool(_RESUME_SYS, f"<이력서>\n{text}\n</이력서>", "submit_skills", _RESUME_SCHEMA,
                                log=log, kind="extract")
    raw = out.get("items", [])
    ms, dropped = [], 0
    for it in raw:
        ev = _locate(it.get("evidence", ""), it.get("mention", ""), text)
        if ev is None:  # 원문에 없는 근거 = 지어낸 것 → 버림
            dropped += 1
            continue
        ms.append({"mention": it["mention"].strip(), "standard_name": (it.get("standard_name") or "").strip(), "evidence": ev,
                   "status": it.get("status") if it.get("status") in RANK else "verify"})
    normalize(ms, log=log, use_embedding=use_embedding, use_llm=use_llm)

    res: dict[str, dict] = {}
    for m in ms:
        for sid in m["skill_ids"]:
            cur = res.get(sid)
            if cur is None or RANK[m["status"]] > RANK[cur["status"]]:
                res[sid] = {"status": m["status"], "evidence": m["evidence"], "mention": m["mention"], "how": m["how"]}
    # 안전망: 사전으로는 잡히는데 LLM이 놓친 스킬은 규칙 판정으로 보탠다
    added = 0
    for sid, v in (extract_resume(text) if safety_net else {}).items():
        if sid not in res:
            res[sid] = {**v, "how": "dict-rule"}
            added += 1
    hows = [m["how"] for m in ms]
    stats = {"mentions": len(raw), "dropped": dropped, "dict": hows.count("dict") + hows.count("dict-std"), "embed_llm": hows.count("llm"),
             "unmatched": hows.count("none"), "safety_net": added,
             "unmatched_mentions": sorted({m["mention"] for m in ms if m["how"] == "none"})[:10]}
    return res, stats


_POSTING_CACHE: dict[str, list[dict]] = {}


def extract_posting_llm(text: str, log=None, use_embedding=True, use_llm=True) -> list[dict]:
    """공고 → extract_posting과 같은 형식. 같은 본문은 다시 호출하지 않는다 (메모리 + 디스크 캐시)."""
    import hashlib
    import json

    from ..adapters import bedrock
    from ..config import DB_PATH, MODEL_ID
    from .normalize import normalize

    # 모델·프롬프트·스키마가 바뀌면 캐시가 무효가 되도록 키에 포함한다
    flags = "" if (use_embedding and use_llm) else f"emb={int(use_embedding)},llm={int(use_llm)}"
    key = hashlib.sha1("\n".join([MODEL_ID, _POSTING_SYS, json.dumps(_POSTING_SCHEMA), flags, text]).encode()).hexdigest()[:16]
    disk = DB_PATH.parent / "posting_cache.json"
    if not _POSTING_CACHE and disk.exists():
        _POSTING_CACHE.update(json.loads(disk.read_text(encoding="utf-8")))
    if key in _POSTING_CACHE:
        return _POSTING_CACHE[key]

    out = bedrock.converse_tool(_POSTING_SYS, f"<공고>\n{text}\n</공고>", "submit_requirements", _POSTING_SCHEMA,
                                log=log, kind="extract")
    ms = []
    for it in out.get("items", []):
        ev = _locate(it.get("evidence", ""), it.get("mention", ""), text)
        if ev is not None:
            ms.append({"mention": it["mention"].strip(), "standard_name": (it.get("standard_name") or "").strip(),
                       "evidence": ev, "section": it.get("section", "required")})
    normalize(ms, log=log, use_embedding=use_embedding, use_llm=use_llm)
    best: dict[str, dict] = {}
    for m in ms:
        req = "preferred" if m["section"] == "preferred" else "required"
        for sid in m["skill_ids"]:
            cur = best.get(sid)
            if cur is None or (cur["requirement"] == "preferred" and req == "required"):
                best[sid] = {"skill_id": sid, "mention": m["mention"], "section": SECTION_LABEL.get(m["section"], "자격요건"),
                             "requirement": req, "evidence": m["evidence"]}
    res = list(best.values())
    _POSTING_CACHE[key] = res
    disk.parent.mkdir(parents=True, exist_ok=True)
    disk.write_text(json.dumps(_POSTING_CACHE, ensure_ascii=False), encoding="utf-8")
    return res


def requirements_from(items: list[dict]) -> dict[str, int]:
    return {m["skill_id"]: 2 if m["requirement"] == "required" else 1 for m in items}
