"""실험: 같은 질의 40개·같은 판정 기준으로 Bedrock Knowledge Base(S3 Vectors, Titan v2 1024) vs 직접 구현 비교.
배포된 리소스는 건드리지 않는다. 새 리소스는 모두 kosa06-kbexp-* 이름 + project=kosa06 태그. 결과·캐시는 이 폴더에만.
    python eval/trust/kb/kb_titan.py build   # AWS 리소스 생성 + 적재 (팀장 승인 뒤에만)
    python eval/trust/kb/kb_titan.py eval    # 검색 + 판정 + 지표
    python eval/trust/kb/cleanup.py          # kosa06-kbexp-* 만 삭제
"""
import json, sys, time, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent / "out"
HERE.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval" / "trust"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from app import config  # noqa: E402

ACCT = "955639821496"
P = "kosa06-kbexp"
TAGS = {"project": "kosa06"}
DIM = 1024
STATE = HERE / "state.json"


def ses():
    s = config.boto_session()
    a = s.client("sts").get_caller_identity()["Account"]
    if a != ACCT or config.AWS_REGION != "ap-northeast-2":
        sys.exit(f"계정/리전 불일치 {a} {config.AWS_REGION}")
    return s


def build():
    from app.rag import retrieve as R
    s = ses()
    region = config.AWS_REGION
    s3, s3v, iam, agent = s.client("s3"), s.client("s3vectors"), s.client("iam"), s.client("bedrock-agent")
    bucket, vbucket, role, kbname = f"{P}-{ACCT}", f"{P}-vec-{ACCT}", f"{P}-role", f"{P}-titan1024"
    for n in (bucket,):
        try:
            s3.head_bucket(Bucket=n)
        except s3.exceptions.ClientError:
            s3.create_bucket(Bucket=n, CreateBucketConfiguration={"LocationConstraint": region})
            s3.put_public_access_block(Bucket=n, PublicAccessBlockConfiguration={
                "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
            s3.put_bucket_tagging(Bucket=n, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]})
    docs = R.corpus()
    idmap = {f"{i:05d}": d["doc_id"] for i, d in enumerate(docs)}
    have = set()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="courses/"):
        have |= {o["Key"] for o in page.get("Contents", [])}
    from concurrent.futures import ThreadPoolExecutor
    def put(i_d):
        i, d = i_d
        key = f"courses/{i:05d}.txt"
        if key not in have:
            s3.put_object(Bucket=bucket, Key=key, Body=d["title"].encode("utf-8"), ContentType="text/plain; charset=utf-8")
    with ThreadPoolExecutor(32) as ex:
        list(ex.map(put, enumerate(docs)))
    print(f"이미 있던 파일 {len(have)}개 재사용")
    (HERE / "idmap.json").write_text(json.dumps(idmap, ensure_ascii=False), encoding="utf-8")
    print(f"업로드 {len(docs)}개 (과정명만, 직접 구현과 같은 텍스트)")
    try:
        s3v.create_vector_bucket(vectorBucketName=vbucket, tags=TAGS)
    except s3v.exceptions.ConflictException:
        pass
    vb_arn = s3v.get_vector_bucket(vectorBucketName=vbucket)["vectorBucket"]["vectorBucketArn"]
    try:
        s3v.create_index(vectorBucketName=vbucket, indexName="courses", dataType="float32", dimension=DIM, distanceMetric="cosine",
                         metadataConfiguration={"nonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]}, tags=TAGS)
    except s3v.exceptions.ConflictException:
        pass
    idx_arn = s3v.get_index(vectorBucketName=vbucket, indexName="courses")["index"]["indexArn"]
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
             "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"aws:SourceAccount": ACCT}}}]}
    try:
        iam.create_role(RoleName=role, AssumeRolePolicyDocument=json.dumps(trust), Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()])
        time.sleep(10)
    except iam.exceptions.EntityAlreadyExistsException:
        pass
    pol = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "bedrock:InvokeModel", "Resource": f"arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v2:0"},
        {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": f"arn:aws:s3:::{bucket}/courses/*"},
        {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": f"arn:aws:s3:::{bucket}"},
        {"Effect": "Allow", "Action": ["s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors",
                                       "s3vectors:QueryVectors", "s3vectors:GetIndex"], "Resource": [idx_arn, vb_arn]}]}
    iam.put_role_policy(RoleName=role, PolicyName="kbexp-access", PolicyDocument=json.dumps(pol))
    role_arn = iam.get_role(RoleName=role)["Role"]["Arn"]
    kb_id = next((k["knowledgeBaseId"] for k in agent.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"] if k["name"] == kbname), None)
    if not kb_id:
        for attempt in range(8):
            try:
                kb_id = agent.create_knowledge_base(
                    name=kbname, roleArn=role_arn, tags=TAGS, description="실험용(배포와 무관): 고용24 과정 검색 비교",
                    knowledgeBaseConfiguration={"type": "VECTOR", "vectorKnowledgeBaseConfiguration": {
                        "embeddingModelArn": f"arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v2:0",
                        "embeddingModelConfiguration": {"bedrockEmbeddingModelConfiguration": {"dimensions": DIM}}}},
                    storageConfiguration={"type": "S3_VECTORS", "s3VectorsConfiguration": {"indexArn": idx_arn}},
                )["knowledgeBase"]["knowledgeBaseId"]
                break
            except agent.exceptions.ValidationException as e:
                if attempt == 7:
                    raise
                print("  역할 전파 대기:", str(e)[:120])
                time.sleep(10)
    while agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]["status"] == "CREATING":
        time.sleep(3)
    ds = agent.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]
    ds_id = ds[0]["dataSourceId"] if ds else agent.create_data_source(
        knowledgeBaseId=kb_id, name="courses",
        dataSourceConfiguration={"type": "S3", "s3Configuration": {"bucketArn": f"arn:aws:s3:::{bucket}", "inclusionPrefixes": ["courses/"]}},
        vectorIngestionConfiguration={"chunkingConfiguration": {"chunkingStrategy": "NONE"}},
    )["dataSource"]["dataSourceId"]
    STATE.write_text(json.dumps({"bucket": bucket, "vbucket": vbucket, "role": role, "kb_id": kb_id, "ds_id": ds_id}), encoding="utf-8")
    jobs = agent.list_ingestion_jobs(knowledgeBaseId=kb_id, dataSourceId=ds_id,
                                     sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"})["ingestionJobSummaries"]
    if jobs and jobs[0]["status"] in ("STARTING", "IN_PROGRESS", "COMPLETE"):
        job = jobs[0]["ingestionJobId"]
        print(f"기존 적재 작업 사용 {job} ({jobs[0]['status']})")
    else:
        job = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]["ingestionJobId"]
    t0 = time.time()
    while True:
        j = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job)["ingestionJob"]
        if j["status"] in ("COMPLETE", "FAILED", "STOPPED"):
            break
        time.sleep(5)
    print(f"적재 {j['status']} {time.time() - t0:.0f}s · {j.get('statistics', {})}")
    if j["status"] != "COMPLETE":
        print(j.get("failureReasons"))


def evaluate():
    import run_retrieval as RR
    from app.rag import retrieve as R
    from app.adapters import bedrock
    st = json.loads(STATE.read_text(encoding="utf-8"))
    idmap = json.loads((HERE / "idmap.json").read_text(encoding="utf-8"))
    byid = {d["doc_id"]: d for d in R.corpus()}
    rt = ses().client("bedrock-agent-runtime")
    CONFIGS = ["bm25", "vector:titan-1024", "vector:cohere-v4"]
    runs = {c: {} for c in CONFIGS + ["kb:titan-1024"]}
    kb_ms = []
    for _, q in RR.QUERIES:
        for c in CONFIGS:
            runs[c][q] = R.search(q, RR.POOL, config=c, exclude_started=False)
        t0 = time.perf_counter()
        out = rt.retrieve(knowledgeBaseId=st["kb_id"], retrievalQuery={"text": q},
                          retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": RR.POOL}})
        kb_ms.append((time.perf_counter() - t0) * 1000)
        docs = []
        for r in out["retrievalResults"]:
            uri = r["location"]["s3Location"]["uri"]
            k = uri.rsplit("/", 1)[-1].split(".")[0]
            docs.append(byid[idmap[k]])
        runs["kb:titan-1024"][q] = docs
    # 판정: 레포 캐시를 복사해서 쓰고, 레포 파일은 건드리지 않는다
    cache_f = HERE / "judge_cache.json"
    if not cache_f.exists():
        shutil.copy(ROOT / "eval" / "trust" / "judge_retrieval.json", cache_f)
    cache = json.loads(cache_f.read_text(encoding="utf-8"))
    before = len(cache)
    # 원래 실험의 7개 조합 풀 + KB 결과로 정답 풀을 만든다 (원래 풀 = 캐시에 있는 판정)
    qrels = {}
    for _, q in RR.QUERIES:
        pool = {d["doc_id"]: d for c in runs for d in runs[c][q]}
        RR.judge(q, list(pool.values()), cache)
        qrels[q] = {k.split("||", 1)[1]: v for k, v in cache.items() if k.startswith(q + "||")}
    cache_f.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"판정: 새로 {len(cache) - before}건 (기존 캐시 {before}건 재사용)")
    per = {}
    for c in runs:
        nd, rc = [], []
        for _, q in RR.QUERIES:
            rel = qrels[q]
            got = [rel.get(d["doc_id"], 0) for d in runs[c][q]]
            n_rel = sum(1 for v in rel.values() if v >= 1)
            nd.append(RR.ndcg(got, list(rel.values())))
            rc.append(sum(1 for v in got[:RR.K] if v >= 1) / min(RR.K, n_rel) if n_rel else 0.0)
        per[c] = {"ndcg@5": nd, "recall@5": rc}
    name_idx = [i for i, (t, _) in enumerate(RR.QUERIES) if t == "name"]
    need_idx = [i for i, (t, _) in enumerate(RR.QUERIES) if t == "need"]
    res = {}
    for c in per:
        v = per[c]["ndcg@5"]
        res[c] = {"ndcg@5": RR.boot(v), "name": RR.boot([v[i] for i in name_idx])[0], "need": RR.boot([v[i] for i in need_idx])[0],
                  "recall@5": RR.boot(per[c]["recall@5"])}
    kb = per["kb:titan-1024"]["ndcg@5"]
    for c in CONFIGS:
        res[c]["kb_minus_this"] = RR.boot([a - b for a, b in zip(kb, per[c]["ndcg@5"])])
    overlap = sum(len({d["doc_id"] for d in runs["kb:titan-1024"][q][:5]} & {d["doc_id"] for d in runs["vector:titan-1024"][q][:5]})
                  for _, q in RR.QUERIES) / (5 * len(RR.QUERIES))
    res["_meta"] = {"at": time.strftime("%Y-%m-%d %H:%M"), "kb_p50_ms": round(sorted(kb_ms)[len(kb_ms) // 2]),
                    "top5_overlap_kb_vs_direct_titan1024": round(overlap, 3),
                    "note": "정답 풀은 원래 7개 조합 + KB 결과. 기존 숫자와 풀이 달라 소수점 둘째 자리가 조금 다를 수 있음"}
    (HERE / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    f = lambda v: f"{v[0]:.3f} [{v[1]:.2f}, {v[2]:.2f}]"  # noqa: E731
    print("| 방식 | nDCG@5 | 이름 질의 | 자연어 질의 | Recall@5 | KB − 이 방식 |")
    for c in ["bm25", "vector:titan-1024", "kb:titan-1024", "vector:cohere-v4"]:
        r = res[c]
        d = r.get("kb_minus_this")
        print(f"| {c} | {f(r['ndcg@5'])} | {r['name']:.3f} | {r['need']:.3f} | {f(r['recall@5'])} | {f(d) if d else '—'} |")
    print(res["_meta"])


if __name__ == "__main__":
    {"build": build, "eval": evaluate}[sys.argv[1]]()
