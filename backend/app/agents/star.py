"""① 강점 진단 (STAR). docs/pivot/CONTRACTS.md 2절.

STAR(상황·과제·행동·결과)는 기업 역량면접(행동사건면접, BEI)에서 경험을 평가하는 표준 방식이다.
- LLM(Bedrock)은 경험을 나누고 각 칸에 들어갈 **이력서 원문 문장**을 고르기만 한다.
- 고른 문장이 원문에 없으면 코드가 버린다(그 칸은 '없음'). 지어낸 근거가 결과에 남지 않는다.
- 점수·수준은 아래 규칙 상수로만 계산한다(AGENTS 규칙 8). 같은 칸이면 같은 점수다.
- BEDROCK_MOCK=1이거나 호출이 실패하면 같은 형식을 문장 패턴 규칙으로 낸다.
"""
import re

from ..adapters import bedrock
from ..skills import sentences

# ── 점수 규칙 (공개 상수) ─────────────────────────────────────────
SLOT_POINT = 1.0          # S·T·A·R 칸마다
QUANT_POINT = 0.5         # 결과(R)에 숫자로 된 성과가 있으면
ROLE_POINT = 0.5          # '내가 한 일'이 드러나면
INFLATED_CAP = 1.0        # 꾸미는 말만 있고 구체적 행동(A)이 없으면 점수 상한
STRONG_MIN, OK_MIN = 4.0, 2.5   # strong: 4점 이상 + A·R 있음 / ok: 2.5점 이상 + A 있음 / 나머지 weak
MAX_SCORE = 4 * SLOT_POINT + QUANT_POINT + ROLE_POINT

SLOTS = ("S", "T", "A", "R")
SLOT_LABEL = {"S": "상황", "T": "과제", "A": "행동", "R": "결과"}

# ── 문장 패턴 (MOCK 판정 + 수치·역할·꾸밈 판정은 Bedrock 모드에서도 이 규칙을 쓴다) ──
_S = re.compile(r"문제|불편|어려움|어려웠|느려|느리|잦|부족|비효율|오류가|장애|병목|요청|필요했|상황|당시|때문에|한계|번거")
_T = re.compile(r"맡아|맡았|맡은|담당|역할|목표|과제|책임|하기로|를 맡|해야 했")
_A = re.compile(r"만들|만든|구현|개발|설계|적용|도입|해결|분석|작성|자동화|리팩터|최적화|구축|배포|수집|전처리|학습시|튜닝|테스트|측정|"
                r"비교|정리|학습하|진행|실험|재현|집계|바꾸|바꿨|옮기|옮겼|연동|캐싱|구성|처리하|컨테이너화|시각화|모델링|크롤링|파인튜닝|운영")
_R = re.compile(r"결과(?:적으로)?[,로 ]+[^.]*(?:되었|됐|했|함|냄)|개선|감소|증가|단축|향상|달성|줄였|줄어|늘었|늘렸|수상|선정|게재|포스터|출판|채택|합격|빨라|0건|%|배\b|→")
_QUANT = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|퍼센트|배|건|초|ms|분|시간|일|주|명|회|원|만원|점|위|개|편|MB|GB|배속|x)|\d+\s*→\s*\d+")
_ROLE = re.compile(r"제가|저는|내가|직접|혼자|단독|맡아|맡았|맡은|담당")
_INFLATED = re.compile(r"혁신적|주도적|주도했|열정|적극적|최고의|탁월|성공적으로|완벽|뛰어난|이끌었|리더십을 발휘")
_SKIP_HEAD = re.compile(r"^\[?(보유\s*기술|기술\s*스택|스킬|자격증?|학력|교육|수료|어학|연락처|인적\s*사항)\]?")
_HEAD = re.compile(r"^\s*\[([^\]]+)\]\s*(.*)$")
_WS = re.compile(r"\s+")

# NCS 직업기초능력 중 경험 문장에서 드러나는 것 (표시용 태그, 점수에 안 씀)
BASIC = {"problem_solving": re.compile(r"해결|원인|개선|최적화|병목"),
         "communication": re.compile(r"발표|설득|문서화|공유|소통|피드백"),
         "teamwork": re.compile(r"협업|팀원|함께|조율|분담"),
         "information": re.compile(r"데이터|분석|수집|시각화"),
         "technology": re.compile(r"구현|개발|설계|배포|자동화|모델")}


def _norm(s: str) -> str:
    return _WS.sub(" ", s or "").strip().lstrip("-•·* ").strip()


def split_experiences(text: str) -> list[dict]:
    """빈 줄·[머리말]·글머리표로 경험 단락을 나눈다. 기술 목록·학력 같은 줄은 경험이 아니다."""
    exps, cur = [], []
    head, skipping = "", False

    def flush():
        body = " ".join(cur).strip()
        if len(body) >= 15:
            title = head or body[:24]
            exps.append({"title": title.strip(), "text": body})
        cur.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        m = _HEAD.match(line)
        if m:  # [머리말] 줄
            flush()
            skipping = bool(_SKIP_HEAD.match(m.group(1)))
            head = "" if skipping else " · ".join(x for x in (m.group(1).strip(), m.group(2).strip()) if x)
            continue  # 머리말 줄의 나머지는 경험 이름이지 내용이 아니다
        if skipping or _SKIP_HEAD.match(line):
            continue
        if line[:1] in "-•·*":  # 글머리표 한 줄 = 경험 하나 (이름: 머리말 · 앞부분)
            flush()
            item = line.lstrip("-•·* ").strip()
            cur.append(item)
            sect = head
            head = f"{sect} · {item[:20]}" if sect else item[:24]
            flush()
            head = sect
            continue
        cur.append(line)  # 일반 문단은 빈 줄까지 한 경험
    flush()
    return [dict(e, exp_id=f"e{i + 1}") for i, e in enumerate(exps)]


def locate(quote: str | None, text: str) -> str | None:
    """인용이 원문에 실제로 있는지. 공백 차이만 허용한다. 없으면 None."""
    q = _norm(quote or "")
    if len(q) < 4:
        return None
    return q if q in _norm(text) else None


def _rule_slots(text: str) -> dict:
    """칸마다 그 칸의 신호가 있는 첫 원문 문장. 한 문장이 행동과 결과를 함께 담으면 두 칸에 같은 문장이 들어간다."""
    sents = sentences(text) or [text]
    pat = {"S": _S, "T": _T, "A": _A, "R": _R}
    return {k: next((s for s in sents if pat[k].search(s)), None) for k in SLOTS}


def score(slots: dict, text: str) -> dict:
    """규칙 점수. slots = {S|T|A|R: 원문 인용 또는 None}."""
    present = {k: bool(slots.get(k)) for k in SLOTS}
    r = slots.get("R") or ""
    quantified = bool(r and _QUANT.search(r))
    role = bool(_ROLE.search(" ".join(v for v in slots.values() if v) or ""))
    a = slots.get("A") or ""
    a_concrete = bool(a and _A.search(_INFLATED.sub("", a)))  # 꾸미는 말을 빼고도 행동 동사가 남는가
    inflated = bool(_INFLATED.search(text)) and not a_concrete
    pts = SLOT_POINT * sum(present.values()) + (QUANT_POINT if quantified else 0) + (ROLE_POINT if role else 0)
    if inflated:
        pts = min(pts, INFLATED_CAP)
    if pts >= STRONG_MIN and present["A"] and present["R"]:
        level = "strong"
    elif pts >= OK_MIN and present["A"]:
        level = "ok"
    else:
        level = "weak"
    missing = [SLOT_LABEL[k] for k in SLOTS if not present[k]]
    hint = []
    if missing:
        hint.append(f"빠진 칸: {'·'.join(missing)}")
    if present["R"] and not quantified:
        hint.append("결과에 숫자가 없음")
    if not role:
        hint.append("내가 한 일이 구분되지 않음")
    if inflated:
        hint.append("꾸미는 말 대신 구체적 행동을 써야 함")
    return {"present": present, "quantified": quantified, "my_role_clear": role, "inflated": inflated,
            "score": round(pts, 2), "level": level, "missing_hint": " · ".join(hint) or None}


def _build(exp: dict, slots: dict) -> dict:
    sc = score(slots, exp["text"])
    body = exp["text"]
    return {"exp_id": exp["exp_id"], "title": exp["title"],
            "slots": {k: ({"quote": slots[k], "present": bool(slots[k]), "quantified": sc["quantified"]} if k == "R"
                          else {"quote": slots[k], "present": bool(slots[k])}) for k in SLOTS},
            "my_role_clear": sc["my_role_clear"], "inflated": sc["inflated"],
            "score": sc["score"], "level": sc["level"],
            "competencies": [b for b, p in BASIC.items() if p.search(body)],
            "missing_hint": sc["missing_hint"]}


_SYS = """너는 기업 역량면접(행동사건면접) 평가자다. 이력서의 각 경험을 STAR로 나눈다.
규칙:
- 경험마다 S(상황·문제), T(맡은 과제·목표), A(내가 한 구체적 행동), R(결과) 칸을 채운다.
- 각 칸에는 이력서 원문 문장을 **글자 그대로** 복사한다. 고치거나 요약하거나 합치지 않는다.
- 원문에 그 칸에 해당하는 문장이 없으면 null. 추측해서 채우지 않는다.
- '혁신적으로 주도했다'처럼 꾸미는 말만 있고 무엇을 했는지 없으면 A는 null이다.
- 기술 목록·학력·자격증 줄은 경험이 아니다."""

_SCHEMA = {"type": "object", "properties": {"experiences": {"type": "array", "items": {
    "type": "object", "properties": {
        "title": {"type": "string", "description": "경험 이름(짧게)"},
        "text": {"type": "string", "description": "이 경험에 해당하는 원문 구간(그대로)"},
        "S": {"type": ["string", "null"]}, "T": {"type": ["string", "null"]},
        "A": {"type": ["string", "null"]}, "R": {"type": ["string", "null"]}},
    "required": ["title", "text", "S", "T", "A", "R"]}}}, "required": ["experiences"]}


def diagnose(resume: str, *, log: "bedrock.CallLog | None" = None, use_llm: bool | None = None) -> tuple[list[dict], dict]:
    """→ (강점 목록, 메타 {mode, dropped_quotes}). resume는 이미 개인정보를 가린 텍스트."""
    use_llm = (bedrock.mode() == "bedrock") if use_llm is None else use_llm
    if use_llm:
        try:
            out = bedrock.converse_tool(_SYS, f"<이력서>\n{resume[:8000]}\n</이력서>", "submit_star", _SCHEMA,
                                        log=log, kind="star", max_tokens=3000)
            res, dropped = [], 0
            for i, e in enumerate(out.get("experiences", [])[:12]):
                text = locate(e.get("text"), resume)
                if text is None:  # 경험 구간 자체가 원문에 없으면 지어낸 경험 → 버림
                    dropped += 1
                    continue
                slots = {}
                for k in SLOTS:
                    q = locate(e.get(k), resume)
                    if e.get(k) and q is None:
                        dropped += 1  # 원문에 없는 인용 → 버림
                    slots[k] = q
                # 칸이 모두 비어도 남긴다: 약한 경험을 숨기지 않고 '약함'으로 보여 준다
                res.append(_build({"exp_id": f"e{i + 1}", "title": e.get("title") or text[:24], "text": text}, slots))
            if res:
                return res, {"mode": "bedrock", "dropped_quotes": dropped}
        except bedrock.BedrockError as err:
            return _rule(resume), {"mode": "rule", "fallback": str(err)[:120], "dropped_quotes": 0}
    return _rule(resume), {"mode": "rule", "dropped_quotes": 0}


def _rule(resume: str) -> list[dict]:
    return [_build(e, _rule_slots(e["text"])) for e in split_experiences(resume)]
