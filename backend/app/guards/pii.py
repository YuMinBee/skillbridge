"""이력서 개인정보 마스킹.

항상 정규식으로 이메일·전화번호·'이름:' 줄을 먼저 가린다.
BEDROCK_MOCK=0이면 이어서 Bedrock Guardrail(adapters/bedrock.guardrail_mask)로 본문 속 이름·주소·나이·URL을 가린다.
(Guardrail은 '지도교수'의 '지도'를 주소로 보는 식의 오탐이 있지만 스킬 추출에는 영향이 없다.)
"""
import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(01[016789]|0\d{1,2})[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")
_NAME_LINE = re.compile(r"^(\s*(?:이름|성명|Name)\s*[:：]\s*)(.+)$", re.MULTILINE | re.IGNORECASE)


def mask(text: str) -> tuple[str, int]:
    n = 0

    def sub(pattern, repl, s):
        nonlocal n
        s2, k = pattern.subn(repl, s)
        n += k
        return s2

    text = sub(_EMAIL, "[이메일]", text)
    text = sub(_PHONE, "[전화번호]", text)
    text = sub(_NAME_LINE, r"\1[이름]", text)
    return text, n
