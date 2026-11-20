"""역량다리 배포 (M6). aws sso login --profile kosa 후:

    python infra/deploy.py            # 계정·리전·만들 리소스만 보여주고 멈춘다
    python infra/deploy.py --yes      # 실제 배포

하는 일
1. 계정 확인 (명세 10절: 다른 팀 계정 주의) — EXPECTED_ACCOUNT와 다르면 중단
2. 데이터 버킷 kosa06-skillbridge-<계정> 생성 (퍼블릭 차단, 암호화, 태그 project=kosa06)
3. 프런트 빌드 → Lambda 패키지(리눅스용 의존성 + backend + seed + 미리 구운 캐시) → S3 업로드
4. raw/ (수집 원본), curated/ (Athena 테이블 데이터) 업로드
5. CloudFormation 스택 kosa06-skillbridge 생성/갱신 (infra/template.yaml) → 시연 주소 출력

비밀 키(WORK24·ALIO)는 Lambda에 넣지 않는다. 수집은 로컬에서만 한다.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import config  # noqa: E402

EXPECTED_ACCOUNT = os.getenv("EXPECTED_ACCOUNT", "955639821496")
STACK = "kosa06-skillbridge"
TAGS = [{"Key": "project", "Value": "kosa06"}]
BUILD = ROOT / "build" / "lambda"
DEPS = ["fastapi>=0.115", "mangum>=0.17", "python-multipart>=0.0.9", "pypdf>=4.0", "python-dotenv>=1.0", "numpy>=1.26", "python-docx>=1.1"]
SEED_PARTS = ["companies", "corp-docs", "courses", "corpus", "market", "personas", "sessions"]


def sh(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


def build_package() -> Path:
    print("[3] 패키지 빌드")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    sh([npm, "run", "build"], cwd=ROOT / "frontend")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_curated.py")], check=True)
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    sh([sys.executable, "-m", "pip", "install", "--quiet", "--target", str(BUILD), "--platform", "manylinux2014_x86_64",
        "--implementation", "cp", "--python-version", "3.12", "--only-binary=:all:", *DEPS])
    ig = shutil.ignore_patterns("__pycache__", "*.pyc", "tests")
    shutil.copytree(ROOT / "backend" / "app", BUILD / "backend" / "app", ignore=ig)
    shutil.copy(ROOT / "data" / "skills.csv", (BUILD / "data").mkdir() or BUILD / "data" / "skills.csv")
    for p in SEED_PARTS:
        if (ROOT / "seed" / p).exists():
            shutil.copytree(ROOT / "seed" / p, BUILD / "seed" / p)
    (BUILD / "eval").mkdir()
    for f in ("results.json", "report.md"):
        if (ROOT / "eval" / f).exists():
            shutil.copy(ROOT / "eval" / f, BUILD / "eval" / f)
    shutil.copytree(ROOT / "frontend" / "dist", BUILD / "frontend" / "dist")
    # 미리 구운 캐시: 시장 인덱스(1분짜리 추출)와 스킬 임베딩. 키가 파일 해시라 같은 파일을 넣으면 그대로 맞는다
    cb = BUILD / "backend" / "cache_bundle"
    cb.mkdir()
    for pat in ("market_index_*.json", "skill_emb_*.json"):
        for f in (ROOT / "backend" / ".data").glob(pat):
            shutil.copy(f, cb / f.name)
    # 교육과정 1,856개 임베딩(검색 최선 조합 하나만). 없으면 Lambda가 콜드스타트마다 전부 다시 임베딩한다
    from app.rag import retrieve  # noqa: E402
    best = retrieve.BEST.split(":")[-1]
    src = ROOT / "backend" / ".data" / "emb" / f"{best}.npz"
    if not src.exists():
        raise SystemExit(f"{src} 없음: 로컬에서 BEDROCK_MOCK=0으로 검색을 한 번 돌려 벡터를 만든 뒤 배포")
    (cb / "emb").mkdir()
    shutil.copy(src, cb / "emb" / src.name)
    (BUILD / "lambda_function.py").write_text(
        "import sys, os\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))\n"
        "from app.main import handler  # noqa: E402,F401\n", encoding="utf-8")
    z = ROOT / "build" / "lambda.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(BUILD.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(BUILD).as_posix())
    print(f"  → {z.relative_to(ROOT)} {z.stat().st_size / 1e6:.1f}MB")
    return z


def ensure_bucket(s3, name):
    print(f"[2] 버킷 {name}")
    try:
        s3.head_bucket(Bucket=name)
        print("  이미 있음")
    except s3.exceptions.ClientError:
        s3.create_bucket(Bucket=name, CreateBucketConfiguration={"LocationConstraint": config.AWS_REGION})
        print("  생성")
    s3.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=name, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
    s3.put_bucket_tagging(Bucket=name, Tagging={"TagSet": TAGS})


def upload_data(s3, bucket):
    print("[4] raw/ · curated/ 업로드")
    n = 0
    for base, prefix in ((ROOT / "backend" / ".data" / "raw", "raw"), (ROOT / "backend" / ".data" / "curated", "curated")):
        for f in base.rglob("*"):
            if f.is_file():
                s3.upload_file(str(f), bucket, f"{prefix}/{f.relative_to(base).as_posix()}")
                n += 1
    print(f"  {n}개 파일")


def deploy_stack(cfn, params):
    print(f"[5] 스택 {STACK}")
    body = (ROOT / "infra" / "template.yaml").read_text(encoding="utf-8")
    kw = dict(StackName=STACK, TemplateBody=body, Capabilities=["CAPABILITY_IAM"], Tags=TAGS,
              Parameters=[{"ParameterKey": k, "ParameterValue": v} for k, v in params.items()])
    try:
        cfn.describe_stacks(StackName=STACK)
        try:
            cfn.update_stack(**kw)
            waiter = "stack_update_complete"
        except cfn.exceptions.ClientError as e:
            if "No updates" in str(e):
                print("  변경 없음")
                return out(cfn)
            raise
    except cfn.exceptions.ClientError as e:
        if "does not exist" not in str(e):
            raise
        cfn.create_stack(**kw, OnFailure="ROLLBACK")
        waiter = "stack_create_complete"
    print("  기다리는 중 (2~4분)…")
    try:
        cfn.get_waiter(waiter).wait(StackName=STACK, WaiterConfig={"Delay": 10, "MaxAttempts": 60})
    except Exception:
        ev = cfn.describe_stack_events(StackName=STACK)["StackEvents"]
        for e in ev[:15]:
            if "FAILED" in e["ResourceStatus"]:
                print("  ✗", e["LogicalResourceId"], e.get("ResourceStatusReason", ""))
        raise
    return out(cfn)


def out(cfn):
    o = {x["OutputKey"]: x["OutputValue"] for x in cfn.describe_stacks(StackName=STACK)["Stacks"][0].get("Outputs", [])}
    print(json.dumps(o, ensure_ascii=False, indent=1))
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--mock", action="store_true", help="Lambda를 BEDROCK_MOCK=1로 (Bedrock 호출 없이)")
    a = ap.parse_args()

    ses = config.boto_session()
    acct = ses.client("sts").get_caller_identity()["Account"]
    print(f"[1] 계정 {acct} · 리전 {config.AWS_REGION} · 프로필 {config.AWS_PROFILE}")
    if acct != EXPECTED_ACCOUNT:
        sys.exit(f"  ✗ 예상 계정 {EXPECTED_ACCOUNT}과 다릅니다. SSO 포털에서 계정을 확인하세요 (EXPECTED_ACCOUNT로 바꿀 수 있음)")
    bucket = f"kosa06-skillbridge-{acct}"
    print(f"  만들 것: S3 {bucket} · Lambda kosa06-skillbridge-api(+함수 URL, 공개, 동시 실행 2) · "
          f"DynamoDB kosa06-skillbridge(온디맨드) · Glue DB kosa06_skillbridge · "
          f"Athena 워크그룹 kosa06-skillbridge · IAM 역할 1개 · 태그 project=kosa06")
    print("  비용 보호: IP당 분당 8회 · 인스턴스당 시간당 Bedrock 20회(넘으면 규칙 엔진) · Athena 쿼리당 1GB")
    print(f"  시연 키: {'설정됨 (' + str(len(config.DEMO_KEY)) + '자) → 공개 방문자는 규칙 엔진, 키 있는 요청만 Bedrock' if config.DEMO_KEY else '없음 → 모든 방문자가 Bedrock 호출 (비용 주의)'}")
    if not a.yes:
        print("  (확인만 했습니다. 배포하려면 --yes)")
        return
    s3 = ses.client("s3")
    ensure_bucket(s3, bucket)
    z = build_package()
    key = f"deploy/lambda-{hashlib.sha1(z.read_bytes()).hexdigest()[:12]}.zip"
    s3.upload_file(str(z), bucket, key)
    upload_data(s3, bucket)
    o = deploy_stack(ses.client("cloudformation"), {
        "DataBucket": bucket, "CodeKey": key, "ModelId": config.MODEL_ID, "FastModelId": config.FAST_MODEL_ID,
        "EmbedModelId": config.EMBED_MODEL_ID, "GuardrailId": config.GUARDRAIL_ID,
        "GuardrailVersion": config.GUARDRAIL_VERSION if config.GUARDRAIL_ID else "",
        "KbId": config.KB_ID, "BedrockMock": "1" if a.mock else "0", "DemoKey": config.DEMO_KEY})
    print(f"\n시연 주소: {o.get('AppUrl')}")


if __name__ == "__main__":
    main()
