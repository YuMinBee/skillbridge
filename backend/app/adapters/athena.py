"""Athena 집계 어댑터 (M3). S3 curated/ 테이블에서 지역·직무별 스킬 언급률을 계산한다.

기준 구현은 pipeline/market.py(로컬 계산)이고, 이 모듈은 같은 숫자를 Athena SQL로 낸다.
ATHENA_WORKGROUP이 비어 있으면 쓰지 않는다. 결과는 프로세스 안에서 캐시한다 (데이터는 수집 때만 바뀐다).
"""
import time
from functools import lru_cache

from ..config import ATHENA_DATABASE, ATHENA_WORKGROUP, boto_session

REGION_KO = {"dg": "대경권", "all": None}


def enabled() -> bool:
    return bool(ATHENA_WORKGROUP)


def _where(region: str, job: str) -> str:
    conds = []
    if job == "public_it":
        conds.append("p.job = 'public' AND contains(p.ncs, '정보통신')")
    else:
        conds.append(f"p.job = '{job}'")
    if REGION_KO.get(region):
        conds.append(f"p.region = '{REGION_KO[region]}'")
    return " AND ".join(conds)


def rates_sql(region: str, job: str) -> str:
    # region·job은 라우터에서 화이트리스트로 검사한 값만 들어온다 (SQL 주입 방지)
    w = _where(region, job)
    return f"""
WITH sel AS (SELECT p.posting_id FROM postings p WHERE {w}),
     n AS (SELECT count(*) AS total FROM sel)
SELECT s.skill_id, count(DISTINCT s.posting_id) * 100.0 / max(n.total) AS pct, max(n.total) AS total
FROM posting_skills s JOIN sel ON s.posting_id = sel.posting_id CROSS JOIN n
GROUP BY s.skill_id ORDER BY pct DESC"""


def query(sql: str, timeout: float = 30) -> tuple[list[dict], dict]:
    ath = boto_session().client("athena")
    t0 = time.time()
    qid = ath.start_query_execution(QueryString=sql, WorkGroup=ATHENA_WORKGROUP,
                                    QueryExecutionContext={"Database": ATHENA_DATABASE})["QueryExecutionId"]
    while True:
        st = ath.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = st["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        if time.time() - t0 > timeout:
            raise TimeoutError(f"Athena {qid} {timeout}s 초과")
        time.sleep(0.4)
    if state != "SUCCEEDED":
        raise RuntimeError(st["Status"].get("StateChangeReason", state))
    rows, token, cols = [], None, None
    while True:
        kw = {"QueryExecutionId": qid, **({"NextToken": token} if token else {})}
        res = ath.get_query_results(**kw)
        data = res["ResultSet"]["Rows"]
        if cols is None:
            cols = [c["VarCharValue"] for c in data[0]["Data"]]
            data = data[1:]
        rows += [{c: d.get("VarCharValue") for c, d in zip(cols, r["Data"])} for r in data]
        token = res.get("NextToken")
        if not token:
            break
    stats = st.get("Statistics", {})
    return rows, {"query_id": qid, "ms": round((time.time() - t0) * 1000),
                  "scanned_mb": round(stats.get("DataScannedInBytes", 0) / 1e6, 2)}


@lru_cache(maxsize=32)
def rates(region: str, job: str) -> tuple[dict[str, float], int, dict]:
    rows, meta = query(rates_sql(region, job))
    total = int(rows[0]["total"]) if rows else 0
    return {r["skill_id"]: float(r["pct"]) for r in rows}, total, meta
