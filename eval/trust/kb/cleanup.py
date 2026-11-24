"""실험 리소스(kosa06-kbexp-*)만 지운다. 배포 스택·기존 KB는 건드리지 않는다."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_titan import ses, P, ACCT
s = ses()
agent, s3, s3v, iam = s.client("bedrock-agent"), s.client("s3"), s.client("s3vectors"), s.client("iam")
for k in agent.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"]:
    if not k["name"].startswith(P + "-"):
        continue
    kid = k["knowledgeBaseId"]
    for d in agent.list_data_sources(knowledgeBaseId=kid)["dataSourceSummaries"]:
        agent.delete_data_source(knowledgeBaseId=kid, dataSourceId=d["dataSourceId"])
    while agent.list_data_sources(knowledgeBaseId=kid)["dataSourceSummaries"]:
        time.sleep(3)
    agent.delete_knowledge_base(knowledgeBaseId=kid)
    print("KB 삭제 요청", k["name"], kid)
    while any(x["knowledgeBaseId"] == kid for x in agent.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"]):
        time.sleep(3)
    print("KB 삭제됨", kid)
vb = f"{P}-vec-{ACCT}"
try:
    for ix in s3v.list_indexes(vectorBucketName=vb)["indexes"]:
        s3v.delete_index(vectorBucketName=vb, indexName=ix["indexName"]); print("인덱스 삭제", ix["indexName"])
    s3v.delete_vector_bucket(vectorBucketName=vb); print("벡터 버킷 삭제", vb)
except s3v.exceptions.NotFoundException:
    print("벡터 버킷 없음")
b = f"{P}-{ACCT}"
try:
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs:
            s3.delete_objects(Bucket=b, Delete={"Objects": objs, "Quiet": True}); n += len(objs)
    s3.delete_bucket(Bucket=b); print("S3 버킷 삭제", b, f"객체 {n}개")
except s3.exceptions.NoSuchBucket:
    print("S3 버킷 없음")
role = f"{P}-role"
try:
    for pn in iam.list_role_policies(RoleName=role)["PolicyNames"]:
        iam.delete_role_policy(RoleName=role, PolicyName=pn); print("정책 삭제", pn)
    iam.delete_role(RoleName=role); print("역할 삭제", role)
except iam.exceptions.NoSuchEntityException:
    print("역할 없음")
# 남은 것 확인
left = [k["name"] for k in agent.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"]]
print("남은 KB:", left)
print("남은 kbexp 버킷:", [x["Name"] for x in s3.list_buckets()["Buckets"] if x["Name"].startswith(P)])
print("남은 kbexp 벡터 버킷:", [x["vectorBucketName"] for x in s3v.list_vector_buckets()["vectorBuckets"] if x["vectorBucketName"].startswith(P)])
