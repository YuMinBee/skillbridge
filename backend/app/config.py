"""환경변수 설정. 저장소 루트의 .env를 읽는다."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip() in ("1", "true", "True", "yes")


# Lambda에서는 SSO 프로필 대신 실행 역할 자격증명을 쓰고, 쓰기는 /tmp만 된다
ON_LAMBDA = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
AWS_PROFILE = "" if ON_LAMBDA else os.getenv("AWS_PROFILE", "kosa")
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
BEDROCK_MOCK = _flag("BEDROCK_MOCK", "1")
DATA_MODE = os.getenv("DATA_MODE", "sample")  # live | sample
MODEL_ID = os.getenv("MODEL_ID", "")
FAST_MODEL_ID = os.getenv("FAST_MODEL_ID", "")
# 설명 생성: Haiku가 Sonnet보다 3배 빠르고 근거 밖 수식어가 적었다 (2026-11-09 비교)
EXPLAIN_MODEL_ID = os.getenv("EXPLAIN_MODEL_ID", "") or FAST_MODEL_ID or MODEL_ID
EMBED_MODEL_ID = os.getenv("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
KB_ID = os.getenv("KB_ID", "")
GUARDRAIL_ID = os.getenv("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.getenv("GUARDRAIL_VERSION", "") or "DRAFT"
DB_PATH = Path(os.getenv("DB_PATH", "/tmp/.data/app.db" if ON_LAMBDA else str(ROOT / "backend" / ".data" / "app.db")))
# 배포 패키지에 미리 구워 넣은 캐시(시장 인덱스·스킬 임베딩). 콜드스타트에 1분짜리 추출을 다시 하지 않게 /tmp로 복사한다
BUNDLED_CACHE = ROOT / "backend" / "cache_bundle"
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "")
ATHENA_DATABASE = os.getenv("ATHENA_DATABASE", "kosa06_skillbridge")
DATA_BUCKET = os.getenv("DATA_BUCKET", "")
# 저장소: sqlite(로컬) | dynamodb(배포, TABLE_NAME)
STORAGE = os.getenv("STORAGE", "sqlite")
TABLE_NAME = os.getenv("TABLE_NAME", "kosa06-skillbridge")
# 원본 기업 설정 쓰기·초기화 허용. 공개 주소(Lambda)에서는 기본 금지 → 방문자 샌드박스에서만 수정
ALLOW_BASE_WRITE = _flag("ALLOW_BASE_WRITE", "0" if ON_LAMBDA else "1")
# 비용 보호: IP당 분당 Bedrock 요청 수, 인스턴스당 시간당 Bedrock 요청 수 (넘으면 그 요청만 규칙 엔진으로)
RATE_PER_MIN = int(os.getenv("RATE_PER_MIN", "8"))
BEDROCK_PER_HOUR = int(os.getenv("BEDROCK_PER_HOUR", "120"))
# 시연 키: 설정하면 X-Demo-Key 헤더가 맞는 요청만 Bedrock을 부르고, 나머지 공개 방문자는 규칙 엔진으로 돈다 (비용 0).
# 값은 .env와 Lambda 환경 변수에만 둔다. 비우면 (로컬 기본) 이 제한이 없다.
DEMO_KEY = os.getenv("DEMO_KEY", "")

SKILLS_CSV = ROOT / "data" / "skills.csv"
SEED = ROOT / "seed"


def boto_session():
    import boto3
    return boto3.Session(profile_name=AWS_PROFILE or None, region_name=AWS_REGION)


if ON_LAMBDA and BUNDLED_CACHE.exists():
    import shutil
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    for f in BUNDLED_CACHE.glob("*.json"):
        if not (DB_PATH.parent / f.name).exists():
            shutil.copy(f, DB_PATH.parent / f.name)
