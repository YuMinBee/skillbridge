"""실험 2: Bedrock Knowledge Base + Cohere Embed v4 (global 추론 프로필, 1536) vs 직접 구현 Cohere v4.
배포된 리소스는 건드리지 않는다. 어제 만든 kosa06-kbexp 버킷·벡터 버킷·역할을 재사용하고,
새로 만드는 것: 벡터 인덱스 courses-c4, 역할 인라인 정책 kbexp-cohere, KB kosa06-kbexp-cohere4(+데이터 소스).
    python eval/trust/kb/kb_cohere.py build   # 2026-11-24: KB 생성 단계에서 거부됨(results_kb_cohere.json)
"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb_titan as K  # noqa: E402
from kb_titan import HERE, ROOT, ACCT, P, TAGS, ses, config  # noqa: E402,F401

DIM = 1536
STATE = HERE / "state_cohere.json"
INDEX = "courses-c4"
KBNAME = f"{P}-cohere4"


def build():
    s = ses()
    region = config.AWS_REGION
    s3v, iam, agent = s.client("s3vectors"), s.client("iam"), s.client("bedrock-agent")
    st1 = json.loads(K.STATE.read_text(encoding="utf-8"))
    bucket, vbucket, role = st1["bucket"], st1["vbucket"], st1["role"]
    try:
        s3v.create_index(vectorBucketName=vbucket, indexName=INDEX, dataType="float32", dimension=DIM, distanceMetric="cosine",
                         metadataConfiguration={"nonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]}, tags=TAGS)
    except s3v.exceptions.ConflictException:
        pass
    idx_arn = s3v.get_index(vectorBucketName=vbucket, indexName=INDEX)["index"]["indexArn"]
    vb_arn = s3v.get_vector_bucket(vectorBucketName=vbucket)["vectorBucket"]["vectorBucketArn"]
    prof_arn = f"arn:aws:bedrock:{region}:{ACCT}:inference-profile/global.cohere.embed-v4:0"
    pol = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "bedrock:InvokeModel",
         "Resource": [prof_arn, "arn:aws:bedrock:*::foundation-model/cohere.embed-v4:0"]},
        {"Effect": "Allow", "Action": "bedrock:GetInferenceProfile", "Resource": prof_arn},
        {"Effect": "Allow", "Action": ["s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors",
                                       "s3vectors:QueryVectors", "s3vectors:GetIndex"], "Resource": [idx_arn, vb_arn]}]}
    iam.put_role_policy(RoleName=role, PolicyName="kbexp-cohere", PolicyDocument=json.dumps(pol))
    role_arn = iam.get_role(RoleName=role)["Role"]["Arn"]
    kb_id = next((k["knowledgeBaseId"] for k in agent.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"] if k["name"] == KBNAME), None)
    if not kb_id:
        last = None
        for attempt in range(6):
            try:
                kb_id = agent.create_knowledge_base(
                    name=KBNAME, roleArn=role_arn, tags=TAGS, description="실험용(배포와 무관): Cohere v4 KB 비교",
                    knowledgeBaseConfiguration={"type": "VECTOR", "vectorKnowledgeBaseConfiguration": {
                        "embeddingModelArn": prof_arn,
                        "embeddingModelConfiguration": {"bedrockEmbeddingModelConfiguration": {"dimensions": DIM}}}},
                    storageConfiguration={"type": "S3_VECTORS", "s3VectorsConfiguration": {"indexArn": idx_arn}},
                )["knowledgeBase"]["knowledgeBaseId"]
                break
            except agent.exceptions.ValidationException as e:
                last = str(e)
                print("  생성 거부:", last[:300])
                if not any(w in last.lower() for w in ("role", "assume", "authorized")):
                    sys.exit("KB_UNSUPPORTED")
                time.sleep(10)
        if not kb_id:
            sys.exit("KB_CREATE_FAILED: " + (last or ""))
    while agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]["status"] == "CREATING":
        time.sleep(3)
    kb = agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]
    print("KB 상태", kb["status"], kb.get("failureReasons"))
    ds = agent.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]
    ds_id = ds[0]["dataSourceId"] if ds else agent.create_data_source(
        knowledgeBaseId=kb_id, name="courses",
        dataSourceConfiguration={"type": "S3", "s3Configuration": {"bucketArn": f"arn:aws:s3:::{bucket}", "inclusionPrefixes": ["courses/"]}},
        vectorIngestionConfiguration={"chunkingConfiguration": {"chunkingStrategy": "NONE"}},
    )["dataSource"]["dataSourceId"]
    STATE.write_text(json.dumps({"kb_id": kb_id, "ds_id": ds_id, "index": INDEX, "kb_name": KBNAME}), encoding="utf-8")
    jobs = agent.list_ingestion_jobs(knowledgeBaseId=kb_id, dataSourceId=ds_id,
                                     sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"})["ingestionJobSummaries"]
    if jobs and jobs[0]["status"] in ("STARTING", "IN_PROGRESS", "COMPLETE"):
        job = jobs[0]["ingestionJobId"]
    else:
        job = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]["ingestionJobId"]
    t0 = time.time()
    while True:
        j = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job)["ingestionJob"]
        if j["status"] in ("COMPLETE", "FAILED", "STOPPED"):
            break
        time.sleep(5)
    print(f"적재 {j['status']} {time.time() - t0:.0f}s · {j.get('statistics', {})}")
    if j["status"] != "COMPLETE" or j.get("statistics", {}).get("numberOfDocumentsFailed"):
        print(j.get("failureReasons"))


def evaluate():
    import shutil
    import run_retrieval as RR
    from app.rag import retrieve as R
    st1 = json.loads(K.STATE.read_text(encoding="utf-8"))
    st2 = json.loads(STATE.read_text(encoding="utf-8"))
    idmap = json.loads((HERE / "idmap.json").read_text(encoding="utf-8"))
    byid = {d["doc_id"]: d for d in R.corpus()}
    rt = ses().client("bedrock-agent-runtime")
    CONFIGS = ["bm25", "vector:titan-1024", "vector:cohere-v4"]
    KBS = {"kb:titan-1024": st1["kb_id"], "kb:cohere-v4": st2["kb_id"]}
    runs = {c: {} for c in CONFIGS + list(KBS)}
    ms = {k: [] for k in KBS}
    for _, q in RR.QUERIES:
        for c in CONFIGS:
            runs[c][q] = R.search(q, RR.POOL, config=c, exclude_started=False)
        for name, kb_id in KBS.items():
            t0 = time.perf_counter()
            out = rt.retrieve(knowledgeBaseId=kb_id, retrievalQuery={"text": q},
                              retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": RR.POOL}})
            ms[name].append((time.perf_counter() - t0) * 1000)
            runs[name][q] = [byid[idmap[r["location"]["s3Location"]["uri"].rsplit("/", 1)[-1].split(".")[0]]]
                             for r in out["retrievalResults"]]
    cache_f = HERE / "judge_cache.json"
    if not cache_f.exists():
        shutil.copy(ROOT / "eval" / "trust" / "judge_retrieval.json", cache_f)
    cache = json.loads(cache_f.read_text(encoding="utf-8"))
    before = len(cache)
    qrels = {}
    for _, q in RR.QUERIES:
        pool = {d["doc_id"]: d for c in runs for d in runs[c][q]}
        RR.judge(q, list(pool.values()), cache)
        qrels[q] = {k.split("||", 1)[1]: v for k, v in cache.items() if k.startswith(q + "||")}
    cache_f.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"판정: 새로 {len(cache) - before}건 (기존 {before}건 재사용)")
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
        res[c] = {"ndcg@5": RR.boot(v), "name": RR.boot([v[i] for i in name_idx])[0],
                  "need": RR.boot([v[i] for i in need_idx])[0], "recall@5": RR.boot(per[c]["recall@5"])}
    kbc = per["kb:cohere-v4"]["ndcg@5"]
    for c in runs:
        if c != "kb:cohere-v4":
            res[c]["kbcohere_minus_this"] = RR.boot([a - b for a, b in zip(kbc, per[c]["ndcg@5"])])
    ov = lambda a, b: sum(len({d["doc_id"] for d in runs[a][q][:5]} & {d["doc_id"] for d in runs[b][q][:5]})  # noqa: E731
                          for _, q in RR.QUERIES) / (5 * len(RR.QUERIES))
    res["_meta"] = {"at": time.strftime("%Y-%m-%d %H:%M"),
                    "p50_ms": {k: round(sorted(v)[len(v) // 2]) for k, v in ms.items()},
                    "top5_overlap_kbcohere_vs_direct_cohere": round(ov("kb:cohere-v4", "vector:cohere-v4"), 3),
                    "top5_overlap_kbtitan_vs_direct_titan": round(ov("kb:titan-1024", "vector:titan-1024"), 3),
                    "note": "정답 풀 = 원래 7개 조합 + KB 2개 결과. KB Cohere는 global 추론 프로필 1536차원, 직접 구현 Cohere도 1536"}
    (HERE / "result_cohere.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    f = lambda v: f"{v[0]:.3f} [{v[1]:.2f}, {v[2]:.2f}]"  # noqa: E731
    print("| 방식 | nDCG@5 | 이름 | 자연어 | Recall@5 | KB-Cohere − 이 방식 |")
    for c in ["bm25", "vector:titan-1024", "kb:titan-1024", "vector:cohere-v4", "kb:cohere-v4"]:
        r = res[c]
        d = r.get("kbcohere_minus_this")
        print(f"| {c} | {f(r['ndcg@5'])} | {r['name']:.3f} | {r['need']:.3f} | {f(r['recall@5'])} | {f(d) if d else '—'} |")
    print(res["_meta"])


if __name__ == "__main__":
    {"build": build, "eval": evaluate}[sys.argv[1]]()
