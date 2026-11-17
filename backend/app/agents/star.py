"""① 강점 진단 (STAR). docs/pivot/CONTRACTS.md 2절.

STAR(상황·과제·행동·결과)는 기업 역량면접(행동사건면접, BEI)에서 경험을 평가하는 표준 방식이다.
- LLM(Bedrock)은 경험을 나누고 각 칸에 들어갈 **이력서 원문 문장**을 고르기만 한다.
- 고른 문장이 원문에 없으면 코드가 버린다(그 칸은 '없음'). 지어낸 근거가 결과에 남지 않는다.
- 점수·수준은 아래 규칙 상수로만 계산한다(AGENTS 규칙 8). 같은 칸이면 같은 점수다.
- BEDROCK_MOCK=1이거나 호출이 실패하면 같은 형식을 문장 패턴 규칙으로 낸다.
"""
import json
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
MAX_EXP = 8               # 화면에 보여 줄 경험 수 상한
MAX_LLM_CHARS = 16_000   # 자소서+포트폴리오를 함께 넣을 수 있게 (이전 8,000)
SLOT_LABEL = {"S": "상황", "T": "과제", "A": "행동", "R": "결과"}

# ── 문장 패턴 (MOCK 판정 + 수치·역할·꾸밈 판정은 Bedrock 모드에서도 이 규칙을 쓴다) ──
_S = re.compile(r"문제|불편|어려움|어려웠|느려|느리|잦|부족|비효율|오류가|장애|병목|요청|필요했|상황|당시|때문에|한계|번거")
_T = re.compile(r"맡아|맡았|맡은|담당|역할|목표|과제|책임|하기로|를 맡|해야 했")
_A = re.compile(r"만들|만든|구현|개발|설계|적용|도입|해결|분석|작성|자동화|리팩터|최적화|구축|배포|수집|전처리|학습시|튜닝|테스트|측정|"
                r"비교|정리|학습하|진행|실험|재현|집계|바꾸|바꿨|옮기|옮겼|연동|캐싱|구성|처리하|컨테이너화|시각화|모델링|크롤링|파인튜닝|운영")
_R = re.compile(r"결과(?:적으로)?[,로 ]+[^.]*(?:되었|됐|했|함|냄)|개선|감소|증가|단축|향상|달성|줄였|줄어|늘었|늘렸|수상|선정|게재|포스터|출판|채택|합격|빨라|0건|%|배\b|→")
# 단위가 붙은 숫자, 'A → B', 'A에서 B로', 지표 이름 + 소수(F1 0.79, nDCG@10 0.41)
_QUANT = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|퍼센트|%p|배|건|초|ms|분|시간|일|주|명|회|원|만원|점|위|개|편|MB|GB|배속|x)"
                    r"|\d[\d.,]*\s*→\s*\d|\d[\d.,]*\s*에서\s*\d[\d.,]*\s*(?:으로|로)"
                    r"|(?:F1|AUC|mAP|IoU|nDCG|Recall|Precision|정확도|정밀도|재현율|BLEU|ROUGE)[^\d]{0,12}\d+\.\d+")
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
    """인용이 원문에 실제로 있는지. 공백·줄바꿈 차이만 허용한다(PDF는 문장 중간에서 줄이 바뀜). 없으면 None."""
    q = _norm(quote or "")
    if len(q) < 4:
        return None
    if q in _norm(text):
        return q
    tight = lambda s: re.sub(r"\s+", "", s)  # noqa: E731  글자는 하나도 다르면 안 된다
    return q if tight(q) in tight(text) else None


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


_SYS = """너는 기업 역량면접(행동사건면접) 평가자다. 지원자의 자기소개서·포트폴리오·이력서에서 경험을 찾아 STAR로 나눈다.
규칙:
- 경험마다 S(상황·문제), T(맡은 과제·목표), A(내가 한 구체적 행동), R(결과) 칸을 채운다.
- 각 칸에는 이력서 원문에서 그 칸의 핵심 문장 **하나만 글자 그대로** 복사한다. 고치거나 요약하거나 여러 문장을 합치지 않는다.
- 원문에 그 칸에 해당하는 문장이 없으면 null. 추측해서 채우지 않는다.
- '혁신적으로 주도했다'처럼 꾸미는 말만 있고 무엇을 했는지 없으면 A는 null이다.
- 기술 목록·학력·자격증·연락처 줄, README의 기능 목록·설치법·폴더 구조는 경험이 아니다.
- 경험은 프로젝트·연구·활동 또는 자기소개서 문항 하나를 한 단위로 묶는다. 같은 프로젝트의 여러 줄은 하나로. 최대 8개.
- 문서 머리말([자기소개서], [GitHub · 레포] 등)이 어느 문서의 경험인지 알려 준다."""

_SCHEMA = {"type": "object", "properties": {"experiences": {"type": "array", "items": {
    "type": "object", "properties": {
        "title": {"type": "string", "description": "경험 이름(짧게)"},
        "anchor": {"type": "string", "description": "이 경험의 첫 문장(원문 그대로, 짧게)"},
        "S": {"type": ["string", "null"]}, "T": {"type": ["string", "null"]},
        "A": {"type": ["string", "null"]}, "R": {"type": ["string", "null"]}},
    "required": ["title", "anchor", "S", "T", "A", "R"]}, "maxItems": MAX_EXP}}, "required": ["experiences"]}


def diagnose(resume: str, *, log: "bedrock.CallLog | None" = None, use_llm: bool | None = None) -> tuple[list[dict], dict]:
    """→ (강점 목록, 메타 {mode, dropped_quotes}). resume는 이미 개인정보를 가린 텍스트."""
    use_llm = (bedrock.mode() == "bedrock") if use_llm is None else use_llm
    if use_llm:
        try:
            out = bedrock.converse_tool(_SYS, f"<이력서>\n{resume[:MAX_LLM_CHARS]}\n</이력서>", "submit_star", _SCHEMA,
                                        log=log, kind="star", max_tokens=8000)
            res, dropped = [], 0
            exps = out.get("experiences", [])
            if isinstance(exps, str):  # 모델이 배열을 JSON 문자열로 주는 경우가 있다(길면 끝이 잘림)
                exps = _salvage(exps)
            if not isinstance(exps, list):
                exps = []
            for i, e in enumerate(x for x in exps[:MAX_EXP] if isinstance(x, dict)):
                e = {k: (v if isinstance(v, str) or v is None else None) for k, v in e.items()}
                slots = {}
                for k in SLOTS:
                    q = locate(e.get(k), resume)
                    if e.get(k) and q is None:
                        dropped += 1  # 원문에 없는 인용 → 버림
                    slots[k] = q
                anchor = locate(e.get("anchor"), resume)
                if anchor is None and not any(slots.values()):  # 원문에서 하나도 확인 안 되면 지어낸 경험 → 버림
                    dropped += 1
                    continue
                text = " ".join(dict.fromkeys(v for v in [anchor, *slots.values()] if v))
                res.append(_build({"exp_id": f"e{i + 1}", "title": e.get("title") or text[:24], "text": text}, slots))
            if res:
                return res, {"mode": "bedrock", "dropped_quotes": dropped}
        except bedrock.BedrockError as err:
            return _rule(resume), {"mode": "rule", "fallback": str(err)[:120], "dropped_quotes": 0}
    return _rule(resume), {"mode": "rule", "dropped_quotes": 0}


def _salvage(s: str) -> list:
    """JSON 배열 문자열 → 리스트. 끝이 잘렸으면 완성된 객체까지만 살린다."""
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except ValueError:
        pass
    dec, out, i = json.JSONDecoder(), [], s.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(s, i)
        except ValueError:
            break
        out.append(obj)
        i = s.find("{", end)
    return out


def _rule(resume: str) -> list[dict]:
    out = [_build(e, _rule_slots(e["text"])) for e in split_experiences(resume)]
    out = [e for e in out if any(s["present"] for s in e["slots"].values()) or e["inflated"]]
    return out[:MAX_EXP]


# ── 우리 STAR 템플릿으로 쓴 경우 ─────────────────────────────────
# 사용자가 칸을 직접 나눠 썼으므로 '어느 칸인가'는 판정하지 않는다. 대신 각 칸의 **질**을 같은 규칙으로 본다:
# 행동(A)에 구체적 행동 동사가 있는가, 결과(R)에 결과·숫자가 있는가, 꾸미는 말뿐인가. 너무 짧은 칸(5자 미만)은 없음으로 본다.
MIN_SLOT = 5


def compose(template: list[dict], skills: str = "") -> str:
    """템플릿 → 이력서 본문(인용·검증용). 칸 문장이 그대로 들어간다."""
    parts = []
    for e in template:
        body = " ".join(_end(e.get(k, "")) for k in SLOTS if (e.get(k) or "").strip())
        parts.append(f"[{e.get('title') or '경험'}]\n{body}")
    if skills.strip():
        parts.append(f"[보유기술] {skills.strip()}")
    return "\n\n".join(parts)


def _end(s: str) -> str:
    s = _norm(s)
    return s if s.endswith((".", "!", "?", "다", "함", "음")) else s + "."


def from_template(template: list[dict], resume: str) -> list[dict]:
    out = []
    for i, e in enumerate(template):
        slots = {}
        for k in SLOTS:
            t = _norm(e.get(k) or "")
            if len(t) < MIN_SLOT:
                slots[k] = None
                continue
            if k == "A" and not _A.search(_INFLATED.sub("", t)):
                slots[k] = t  # 칸은 채웠지만 구체적 행동이 없으면 score()의 꾸밈 규칙이 상한을 건다
            elif k == "R" and not (_R.search(t) or _QUANT.search(t)):
                slots[k] = None  # '열심히 했다'처럼 결과가 아닌 문장은 결과로 치지 않는다
                continue
            slots[k] = locate(t, resume) or locate(_end(t), resume)
        text = " ".join(v for v in slots.values() if v) or (e.get("title") or "")
        out.append(_build({"exp_id": f"e{i + 1}", "title": e.get("title") or f"경험 {i + 1}", "text": text}, slots))
    return out
