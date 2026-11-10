"""이력서 PII 마스킹용 Bedrock Guardrail을 만들거나 기존 것을 찾는다 (멱등).

실행: python scripts/create_guardrail.py  → 출력된 GUARDRAIL_ID/VERSION을 .env에 넣는다.
태그 project=kosa06. 콘텐츠 필터는 쓰지 않고 PII 익명화(한국어 이름·주소 포함 확인)와 주민번호 정규식만 둔다.
2026-11-09 생성: 9riz99g8yu0l, 사용 버전 2.
"""
import sys
import time

import boto3

NAME = "kosa06-skillbridge-pii"
TAGS = [{"key": "project", "value": "kosa06"}]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(profile="kosa", region="ap-northeast-2"):
    bd = boto3.Session(profile_name=profile, region_name=region).client("bedrock")
    F = {"action": "ANONYMIZE", "inputAction": "ANONYMIZE", "outputAction": "ANONYMIZE",
         "inputEnabled": True, "outputEnabled": True}  # input 쪽을 명시하지 않으면 ApplyGuardrail(INPUT)에서 아무것도 가리지 않는다
    cfg = dict(
        name=NAME,
        description="역량다리(06팀) 이력서 개인정보 익명화",
        blockedInputMessaging="개인정보가 포함되어 처리할 수 없습니다.",
        blockedOutputsMessaging="개인정보가 포함되어 처리할 수 없습니다.",
        sensitiveInformationPolicyConfig={
            "piiEntitiesConfig": [{"type": t, **F} for t in
                                  ["NAME", "EMAIL", "PHONE", "ADDRESS", "AGE", "URL", "USERNAME", "PASSWORD"]],
            # 전화번호는 내장 PHONE이 한국 번호도 잡는다. 주민번호만 정규식으로 보탠다.
            "regexesConfig": [{"name": "KR_RRN", "description": "주민등록번호", "pattern": r"\d{6}[- ]?[1-4]\d{6}", **F}],
        },
    )
    found = [g for g in bd.list_guardrails()["guardrails"] if g["name"] == NAME]
    if found:
        gid = found[0]["id"]
        bd.update_guardrail(guardrailIdentifier=gid, **cfg)
        print("기존 Guardrail 갱신:", gid)
    else:
        gid = bd.create_guardrail(**cfg, tags=TAGS)["guardrailId"]
        print("생성:", gid)
    for _ in range(30):
        if bd.get_guardrail(guardrailIdentifier=gid)["status"] == "READY":
            break
        time.sleep(2)
    v = bd.create_guardrail_version(guardrailIdentifier=gid, description="published by create_guardrail.py")["version"]
    print(f"\n.env에 추가:\nGUARDRAIL_ID={gid}\nGUARDRAIL_VERSION={v}")


if __name__ == "__main__":
    main()
