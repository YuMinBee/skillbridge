"""작업(job) 저장·실행. 질문을 job으로 접수하면 브라우저를 닫아도 서버에서 끝까지 돈다.

- 저장: 로컬 SQLite(jobs 테이블) / 배포 DynamoDB(pk=JOB, sk=job_id, ttl 24시간). 이력서 원문은 저장하지 않는다.
- 실행: 로컬은 백그라운드 스레드(contextvars 복사 → 요청별 예산·폴백 상태 유지).
        Lambda는 자기 자신을 비동기 호출(InvocationType=Event) → main.handler가 job 이벤트를 받아 실행.
"""
import contextvars
import json
import os
import re
import threading
import time
import uuid

from .. import config
from . import bedrock, storage

_ID = re.compile(r"^j_[0-9a-f]{12}$")


def valid_id(job_id: str) -> bool:
    return bool(_ID.match(job_id or ""))


# ── 저장소 ─────────────────────────────────────────────────────────
def _sqlite_conn(b):
    c = b.conn()
    c.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL)")
    return c


def _save(job: dict):
    b = storage.backend()
    job["updated"] = time.time()
    data = json.dumps(job, ensure_ascii=False)
    if b.name == "sqlite":
        with b.lock, _sqlite_conn(b) as c:
            c.execute("DELETE FROM jobs WHERE created < ?", (time.time() - config.JOB_TTL,))
            c.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?, ?)", (job["job_id"], data, job["created"]))
    else:
        b._put("JOB", job["job_id"], data=data, ttl=int(job["created"] + config.JOB_TTL))


def get(job_id: str) -> dict | None:
    if not valid_id(job_id):
        return None
    b = storage.backend()
    if b.name == "sqlite":
        with _sqlite_conn(b) as c:
            r = c.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return json.loads(r[0]) if r else None
    r = b.c.get_item(TableName=b.table, Key={"pk": {"S": "JOB"}, "sk": {"S": job_id}}, ConsistentRead=True)
    it = r.get("Item")
    if not it or float(it.get("ttl", {}).get("N", "0")) < time.time():
        return None
    return json.loads(it["data"]["S"])


def create(job_family: str) -> dict:
    job = {"job_id": f"j_{uuid.uuid4().hex[:12]}", "status": "queued", "job_family": job_family,
           "created": time.time(), "progress": [], "result": None, "citations": [], "cost": None, "trace": []}
    _save(job)
    return job


# ── 실행 ───────────────────────────────────────────────────────────
def run(job_id: str, payload: dict):
    """job 하나를 끝까지 실행한다. payload의 resume은 정규식 마스킹이 끝난 본문이고, 저장하지 않는다."""
    from ..agents import supervisor
    job = get(job_id) or {"job_id": job_id, "created": time.time()}
    job["status"] = "running"
    _save(job)
    token = bedrock.force_mock(payload["force_mock"]) if payload.get("force_mock") else None

    def on_progress(progress):
        job["progress"] = progress
        _save(job)

    try:
        out = supervisor.run(payload, on_progress=on_progress)
        job.update(status="done", progress=out["progress"], result=out["result"], citations=out["citations"],
                   cost=out["cost"], trace=out["trace"], verify=out.get("verify"), mode=bedrock.mode())
    except supervisor.NoInput as e:  # 사용자 입력 문제: 내부 예외 이름 없이 안내 문장만
        job.update(status="failed", error=str(e))
    except Exception as e:  # noqa: BLE001
        job.update(status="failed", error=f"{type(e).__name__}: {str(e)[:200]}")
    finally:
        if token is not None:
            bedrock._force_mock.reset(token)
    _save(job)
    return job


def submit(job_id: str, payload: dict, sync: bool = False):
    if bedrock.forced_reason():
        payload = dict(payload, force_mock=bedrock.forced_reason())
    if sync or os.getenv("JOB_SYNC") == "1":
        return run(job_id, payload)
    if config.ON_LAMBDA:
        import boto3
        boto3.client("lambda").invoke(FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"], InvocationType="Event",
                                      Payload=json.dumps({"skillbridge_job": job_id, "payload": payload}).encode())
        return None
    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(run, job_id, payload), daemon=True).start()
    return None
