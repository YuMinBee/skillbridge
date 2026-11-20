"""Bedrock 어댑터.

BEDROCK_MOCK=1이면 AWS를 호출하지 않고 템플릿/규칙으로 같은 형식의 결과를 낸다.
BEDROCK_MOCK=0이면 Converse API(도구 호출로 구조화 출력), Titan 임베딩, ApplyGuardrail을 쓴다.
호출마다 모델·토큰·소요시간을 CallLog에 남겨 trace에 표시한다.
"""
import json
import re
import time
from contextvars import ContextVar
from functools import lru_cache

from ..config import AWS_PROFILE, AWS_REGION, BEDROCK_MOCK, EMBED_MODEL_ID, EXPLAIN_MODEL_ID, FAST_MODEL_ID, GUARDRAIL_ID, \
    GUARDRAIL_VERSION, MODEL_ID

_CITE = re.compile(r"\[(E\d+)\]")
BEDROCK_READY = True
# 비용 상한을 넘은 요청은 이 요청만 규칙 엔진으로 돈다 (guards/limits.py가 설정)
_force_mock: ContextVar[str | None] = ContextVar("force_mock", default=None)


class BedrockError(RuntimeError):
    """호출 실패. 파이프라인은 이 예외를 받으면 규칙 기반으로 폴백한다."""


def mode() -> str:
    if _force_mock.get():
        return "mock"
    return "bedrock" if (not BEDROCK_MOCK and BEDROCK_READY and MODEL_ID) else "mock"


def configured_mode() -> str:
    """요청별 상한과 무관한 설정상의 모드 (배지 표시용)."""
    return "bedrock" if (not BEDROCK_MOCK and BEDROCK_READY and MODEL_ID) else "mock"


def force_mock(reason: str):
    return _force_mock.set(reason)


def forced_reason() -> str | None:
    return _force_mock.get()


@lru_cache(maxsize=1)
def client():
    import boto3  # 지연 import: mock 모드에서는 AWS 자격증명이 없어도 된다
    from botocore.config import Config
    cfg = Config(read_timeout=90, connect_timeout=10, retries={"max_attempts": 4, "mode": "adaptive"})
    return boto3.Session(profile_name=AWS_PROFILE or None, region_name=AWS_REGION).client("bedrock-runtime", config=cfg)


def short_model(model_id: str) -> str:
    """trace 표시용: 'global.anthropic.claude-sonnet-4-6' → 'claude-sonnet-4-6'"""
    return model_id.split("anthropic.")[-1].split("amazon.")[-1]


class CallLog:
    """한 진단 요청 동안의 Bedrock 호출 기록."""

    def __init__(self):
        self.calls: list[dict] = []

    def add(self, kind: str, model: str, ms: float, tin: int = 0, tout: int = 0):
        self.calls.append({"kind": kind, "model": short_model(model), "ms": round(ms), "in": tin, "out": tout})

    def since(self, i: int) -> list[dict]:
        return self.calls[i:]


def _wrap(e: Exception) -> BedrockError:
    name = type(e).__name__
    msg = str(e)
    if "SSO" in name or "Token" in name or "ExpiredToken" in msg or "sso" in msg.lower():
        return BedrockError("AWS 로그인 만료 · `aws sso login --profile kosa` 실행 필요")
    return BedrockError(f"{name}: {msg[:200]}")


def converse_tool(system: str, user: str, tool_name: str, schema: dict, *, model: str | None = None,
                  log: CallLog | None = None, max_tokens: int = 4000, kind: str = "converse") -> dict:
    """도구 호출을 강제해 JSON 스키마에 맞는 입력(dict)을 받는다."""
    model = model or MODEL_ID
    t0 = time.perf_counter()
    try:
        r = client().converse(
            modelId=model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            toolConfig={"tools": [{"toolSpec": {"name": tool_name, "description": "결과를 이 형식으로 제출한다.",
                                                "inputSchema": {"json": schema}}}],
                        "toolChoice": {"tool": {"name": tool_name}}},
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
        )
    except Exception as e:  # noqa: BLE001
        raise _wrap(e) from e
    u = r.get("usage", {})
    if log is not None:
        log.add(kind, model, (time.perf_counter() - t0) * 1000, u.get("inputTokens", 0), u.get("outputTokens", 0))
    for c in r["output"]["message"]["content"]:
        if "toolUse" in c:
            return c["toolUse"]["input"]
    raise BedrockError("구조화 출력 없음")


def converse_turn(system: str, messages: list[dict], tools: list[dict], *, model: str | None = None,
                  log: CallLog | None = None, max_tokens: int = 1500, kind: str = "agent") -> dict:
    """도구를 고를 수 있는 한 턴 (에이전트 루프용). → 모델 메시지 {role, content}"""
    model = model or FAST_MODEL_ID or MODEL_ID
    t0 = time.perf_counter()
    try:
        r = client().converse(
            modelId=model, system=[{"text": system}], messages=messages,
            toolConfig={"tools": [{"toolSpec": t} for t in tools], "toolChoice": {"auto": {}}},
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
        )
    except Exception as e:  # noqa: BLE001
        raise _wrap(e) from e
    u = r.get("usage", {})
    if log is not None:
        log.add(kind, model, (time.perf_counter() - t0) * 1000, u.get("inputTokens", 0), u.get("outputTokens", 0))
    return r["output"]["message"]


def embed(texts: list[str], log: CallLog | None = None, dims: int = 512) -> list[list[float]]:
    """Titan V2 임베딩 (정규화된 벡터). 동시에 몇 개씩 호출한다."""
    from concurrent.futures import ThreadPoolExecutor

    def one(t):
        r = client().invoke_model(modelId=EMBED_MODEL_ID,
                                  body=json.dumps({"inputText": t[:2000], "dimensions": dims, "normalize": True}))
        return json.loads(r["body"].read())["embedding"]

    t0 = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            out = list(ex.map(one, texts))
    except Exception as e:  # noqa: BLE001
        raise _wrap(e) from e
    if log is not None and texts:
        log.add("embed", EMBED_MODEL_ID, (time.perf_counter() - t0) * 1000, len(texts), 0)
    return out


def guardrail_mask(text: str, log: CallLog | None = None) -> tuple[str, int]:
    """ApplyGuardrail(PII ANONYMIZE). GUARDRAIL_ID가 없으면 그대로 돌려준다."""
    if not GUARDRAIL_ID:
        return text, 0
    t0 = time.perf_counter()
    try:
        r = client().apply_guardrail(guardrailIdentifier=GUARDRAIL_ID, guardrailVersion=GUARDRAIL_VERSION,
                                     source="INPUT", content=[{"text": {"text": text}}])
    except Exception as e:  # noqa: BLE001
        raise _wrap(e) from e
    if log is not None:
        log.add("guardrail", "guardrail", (time.perf_counter() - t0) * 1000)
    if r.get("action") != "GUARDRAIL_INTERVENED":
        return text, 0
    n = 0
    for a in r.get("assessments", []):
        n += len(a.get("sensitiveInformationPolicy", {}).get("piiEntities", []))
        n += len(a.get("sensitiveInformationPolicy", {}).get("regexes", []))
    outs = r.get("outputs") or []
    masked = outs[0]["text"] if outs else text
    for k, v in _PII_LABEL.items():
        masked = masked.replace("{" + k + "}", v)
    masked, undone = undo_midword_address(text, masked)
    return masked, n - undone


_HANGUL = re.compile(r"[가-힣]")
# Guardrail이 주소로 잘못 가린 것이 확인된 일반 단어. 발견될 때마다 추가하고 DECISIONS에 적는다.
NOT_ADDRESS = {"동아리"}


def undo_midword_address(before: str, after: str) -> tuple[str, int]:
    """Guardrail이 단어 중간을 주소로 가린 오탐을 되돌린다. 예: '동아리' → '[주소]리' → '동아리'.
    되돌리는 조건: [주소] 라벨만이고, (가려진 원문이 NOT_ADDRESS 단어) 또는 (모두 만족: 바로 뒤에 한글이 붙어 있음, 가려진 원문에 공백·숫자가 없고 6자 이하).
    번지가 있는 진짜 주소('대구 북구 침산로 12')는 공백·숫자가 있어 그대로 가린다. 이름은 되돌리지 않는다('[이름]님'은 진짜 이름)."""
    from difflib import SequenceMatcher
    label = _PII_LABEL["ADDRESS"]
    if label not in after:
        return after, 0
    out, k = [], 0
    for op, i1, i2, j1, j2 in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        seg_after, seg_before = after[j1:j2], before[i1:i2]
        midword = (j2 < len(after) and _HANGUL.match(after[j2]) and seg_before and len(seg_before) <= 6
                   and not re.search(r"[\s\d]", seg_before))
        if op == "replace" and seg_after == label and (midword or seg_before.strip() in NOT_ADDRESS):
            out.append(seg_before)
            k += 1
        else:
            out.append(seg_after)
    return "".join(out), k


_PII_LABEL = {"NAME": "[이름]", "ADDRESS": "[주소]", "AGE": "[나이]", "URL": "[URL]", "EMAIL": "[이메일]",
              "PHONE": "[전화번호]", "USERNAME": "[아이디]", "PASSWORD": "[비밀번호]", "KR_RRN": "[주민번호]"}


def cites_valid(text: str, allowed: set[str]) -> bool:
    """설명문이 근거 ID를 최소 1개 인용하고, 없는 ID를 지어내지 않았는지."""
    cited = set(_CITE.findall(text))
    return bool(cited) and cited <= allowed


def template_why(step: dict, evidence: dict[str, dict]) -> str:
    """LLM 없이 근거를 이어 붙인 설명 (목업·폴백용)."""
    parts = []
    for eid in step.get("evidence_ids", []):
        e = evidence[eid]
        if e["type"] in ("apply", "corp", "market", "plan"):
            parts.append(f"{e['text']} [{eid}]")
        elif e["type"] == "resume":
            parts.append(f"이력서 근거: “{e['text']}” [{eid}]")
        elif e["type"] == "posting":
            parts.append(f"공고 문장: “{e['text']}” [{eid}]")
    return " · ".join(parts)


def explain_step(step: dict, evidence: dict[str, dict]) -> str:
    """하위호환: 단계 하나의 템플릿 설명."""
    return template_why(step, evidence)


_EXPLAIN_SYS = """너는 취업 준비생에게 학습경로의 각 단계를 왜 추천하는지 설명한다.
규칙:
- 단계마다 한국어 1~2문장, 존댓말(~해요체).
- 그 단계에 주어진 근거만 사용하고, 사용한 근거 뒤에 [E1]처럼 근거 ID를 붙인다. 최소 1개는 반드시 인용한다.
- 그 단계 목록에 없는 근거 ID, 근거에 없는 숫자·회사·과정 이름을 만들지 않는다.
- 근거가 말하지 않는 평가(높다, 핵심, 필수적이다 등)를 덧붙이지 않는다. 숫자는 근거에 있는 그대로 쓴다.
- 점수나 합격 가능성을 판단하지 않는다."""

_EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"step": {"type": "integer"}, "why": {"type": "string"}},
        "required": ["step", "why"]}}},
    "required": ["items"],
}

_KIND = {"public": "공공 교육과정", "corp": "기업 교육 트랙", "proof": "결과물로 증명하기", "self": "자습"}


def explain_steps(steps: list[dict], evidence: dict[str, dict], company_name: str, log: CallLog | None = None,
                  model: str | None = None) -> tuple[list[str], int]:
    """학습경로 전체 단계의 설명을 한 번에 생성한다. 인용이 틀린 단계는 한 번 재생성하고,
    그래도 틀리면 템플릿으로 대체한다. → (설명 목록, 템플릿으로 대체한 수)"""

    def ask(idx: list[int], note: str = "") -> dict[int, str]:
        lines = [f"기업: {company_name}", note]
        for i in idx:
            st = steps[i]
            lines.append(f"\n[단계 {i}] {st['skill']} · {_KIND.get(st['kind'], st['kind'])} · {st['title']} · {st['hours']}시간")
            for eid in st["evidence_ids"]:
                lines.append(f"  - {eid} ({evidence[eid]['type']}): {evidence[eid]['text']}")
        out = converse_tool(_EXPLAIN_SYS, "\n".join(lines), "submit_explanations", _EXPLAIN_SCHEMA,
                            model=model or EXPLAIN_MODEL_ID, log=log, max_tokens=3000, kind="explain")
        return {int(x["step"]): x["why"].strip() for x in out.get("items", []) if "step" in x and "why" in x}

    result: dict[int, str] = ask(list(range(len(steps))))
    bad = [i for i in range(len(steps)) if not cites_valid(result.get(i, ""), set(steps[i]["evidence_ids"]))]
    if bad:
        result.update(ask(bad, "주의: 직전 답에서 근거 ID 인용이 없거나 목록에 없는 ID를 썼다. 각 단계 목록의 ID만 인용하라."))
    n_fallback = 0
    whys = []
    for i, st in enumerate(steps):
        w = result.get(i, "")
        if not cites_valid(w, set(st["evidence_ids"])):
            w = template_why(st, evidence)
            n_fallback += 1
        whys.append(w)
    return whys, n_fallback
