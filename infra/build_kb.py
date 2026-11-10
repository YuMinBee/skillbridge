"""기업 지식베이스 생성 (M4): S3 Vectors 버킷·인덱스 → IAM 역할 → Bedrock KB → S3 데이터 소스 → 적재 → 격리 검증.

    python infra/build_kb.py          # 계정·만들 것만 보여주고 멈춘다
    python infra/build_kb.py --yes    # 생성(이미 있으면 재사용) + 문서 업로드 + 적재 + 검증

- 벡터 저장소는 S3 Vectors (OpenSearch Serverless 금지: 상시 OCU 과금)
- 문서: seed/corp-docs/{tenant}/*.md → s3://<데이터 버킷>/corp-docs/{tenant}/ + .metadata.json {tenantId}
- 끝나면 KB_ID를 출력한다. .env의 KB_ID= 에 넣으면 앱이 KB 검색을 쓴다.
- 검증: A사 고유 문구를 B사 필터로 검색하면 0건이어야 한다.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import config  # noqa: E402

EXPECTED_ACCOUNT = "955639821496"
NAME = "kosa06-skillbridge-kb"
TAGS = {"project": "kosa06"}
DIM = 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    ses = config.boto_session()
    acct = ses.client("sts").get_caller_identity()["Account"]
    region = config.AWS_REGION
    print(f"[1] 계정 {acct} · 리전 {region}")
    if acct != EXPECTED_ACCOUNT:
        sys.exit("  ✗ 예상 계정이 아닙니다")
    data_bucket = f"kosa06-skillbridge-{acct}"
    vbucket = f"kosa06-skillbridge-vec-{acct}"
    print(f"  만들 것: S3 Vectors {vbucket}/corp-docs({DIM}차원, cosine) · IAM 역할 {NAME}-role · KB {NAME} · "
          f"데이터 소스 s3://{data_bucket}/corp-docs/ · 태그 project=kosa06")
    if not a.yes:
        print("  (확인만 했습니다. 만들려면 --yes)")
        return

    s3, s3v, iam = ses.client("s3"), ses.client("s3vectors"), ses.client("iam")
    agent = ses.client("bedrock-agent")
    try:
        s3.head_bucket(Bucket=data_bucket)
    except s3.exceptions.ClientError:
        sys.exit(f"  ✗ 데이터 버킷 {data_bucket}이 없습니다. 먼저 python infra/deploy.py --yes")

    print("[2] 문서 업로드 (tenantId 메타데이터)")
    n = 0
    for f in sorted((ROOT / "seed" / "corp-docs").glob("*/*.md")):
        tid = f.parent.name
        key = f"corp-docs/{tid}/{f.name}"
        s3.upload_file(str(f), data_bucket, key)
        s3.put_object(Bucket=data_bucket, Key=key + ".metadata.json",
                      Body=json.dumps({"metadataAttributes": {"tenantId": tid}}).encode())
        n += 1
    print(f"  {n}개")

    print("[3] S3 Vectors")
    try:
        s3v.create_vector_bucket(vectorBucketName=vbucket, tags=TAGS)
    except s3v.exceptions.ConflictException:
        pass
    vb_arn = s3v.get_vector_bucket(vectorBucketName=vbucket)["vectorBucket"]["vectorBucketArn"]
    try:
        s3v.create_index(vectorBucketName=vbucket, indexName="corp-docs", dataType="float32", dimension=DIM,
                         distanceMetric="cosine",
                         metadataConfiguration={"nonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]},
                         tags=TAGS)
    except s3v.exceptions.ConflictException:
        pass
    idx_arn = s3v.get_index(vectorBucketName=vbucket, indexName="corp-docs")["index"]["indexArn"]

    print("[4] IAM 역할")
    role = f"{NAME}-role"
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
                                                     "Action": "sts:AssumeRole",
                                                     "Condition": {"StringEquals": {"aws:SourceAccount": acct}}}]}
    try:
        iam.create_role(RoleName=role, AssumeRolePolicyDocument=json.dumps(trust),
                        Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()])
        time.sleep(10)  # 역할 전파
    except iam.exceptions.EntityAlreadyExistsException:
        pass
    pol = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "bedrock:InvokeModel",
         "Resource": f"arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v2:0"},
        {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": f"arn:aws:s3:::{data_bucket}/corp-docs/*"},
        {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": f"arn:aws:s3:::{data_bucket}",
         "Condition": {"StringLike": {"s3:prefix": ["corp-docs/*"]}}},
        {"Effect": "Allow", "Action": ["s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors",
                                       "s3vectors:QueryVectors", "s3vectors:GetIndex"], "Resource": [idx_arn, vb_arn]}]}
    iam.put_role_policy(RoleName=role, PolicyName="kb-access", PolicyDocument=json.dumps(pol))
    role_arn = iam.get_role(RoleName=role)["Role"]["Arn"]

    print("[5] Knowledge Base")
    kb_id = next((k["knowledgeBaseId"] for k in agent.list_knowledge_bases()["knowledgeBaseSummaries"] if k["name"] == NAME), None)
    if not kb_id:
        for attempt in range(6):  # 역할 전파 지연 대비
            try:
                kb_id = agent.create_knowledge_base(
                    name=NAME, roleArn=role_arn, tags=TAGS,
                    knowledgeBaseConfiguration={"type": "VECTOR", "vectorKnowledgeBaseConfiguration": {
                        "embeddingModelArn": f"arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v2:0",
                        "embeddingModelConfiguration": {"bedrockEmbeddingModelConfiguration": {"dimensions": DIM}}}},
                    storageConfiguration={"type": "S3_VECTORS", "s3VectorsConfiguration": {"indexArn": idx_arn}},
                )["knowledgeBase"]["knowledgeBaseId"]
                break
            except agent.exceptions.ValidationException as e:
                if attempt == 5 or "role" not in str(e).lower():
                    raise
                time.sleep(10)
    while agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]["status"] == "CREATING":
        time.sleep(3)
    ds = agent.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]
    ds_id = ds[0]["dataSourceId"] if ds else agent.create_data_source(
        knowledgeBaseId=kb_id, name="corp-docs",
        dataSourceConfiguration={"type": "S3", "s3Configuration": {
            "bucketArn": f"arn:aws:s3:::{data_bucket}", "inclusionPrefixes": ["corp-docs/"]}},
        vectorIngestionConfiguration={"chunkingConfiguration": {"chunkingStrategy": "FIXED_SIZE",
                                                                "fixedSizeChunkingConfiguration": {"maxTokens": 200, "overlapPercentage": 10}}},
    )["dataSource"]["dataSourceId"]

    print("[6] 적재")
    job = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]["ingestionJobId"]
    while True:
        j = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job)["ingestionJob"]
        if j["status"] in ("COMPLETE", "FAILED", "STOPPED"):
            break
        time.sleep(4)
    print(f"  {j['status']} · {j.get('statistics', {})}")
    if j["status"] != "COMPLETE":
        sys.exit(f"  ✗ {j.get('failureReasons')}")

    print("[7] 격리 검증")
    import app.adapters.kb as kb
    kb.KB_ID = kb_id
    rt = ses.client("bedrock-agent-runtime")
    own = kb.retrieve("A", "경산 공장 온보딩 라벨링", k=3, client=rt)
    leak = [r for r in kb.retrieve("B", "경산 공장 온보딩 라벨링", k=5, client=rt) if "경산" in r["text"]]
    print(f"  A로 검색: {len(own)}건 (경산 포함 {sum('경산' in r['text'] for r in own)}) · B로 같은 질의: A 문서 {len(leak)}건")
    if leak:
        sys.exit("  ✗ 다른 tenant 문서가 검색됨")
    print(f"\nKB_ID={kb_id}  ← .env에 넣으세요 (배포 시 Lambda 환경변수로 전달됨)")


if __name__ == "__main__":
    main()
