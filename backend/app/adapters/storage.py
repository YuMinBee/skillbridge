"""로컬 모드 저장소 (SQLite). 기업 설정·트랙과 익명 진단 집계만 저장한다.

이력서 원문이나 개인 식별 정보는 저장하지 않는다. 배포 시 DynamoDB 어댑터로 교체 가능하게
함수 단위 인터페이스만 노출한다.
"""
import json
import sqlite3
import threading
from copy import deepcopy
from datetime import datetime, timezone

from ..config import DB_PATH
from ..data import seed_companies

_lock = threading.Lock()


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS companies (tenant_id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT, gaps TEXT, created TEXT)")
    cols = {r[1] for r in c.execute("PRAGMA table_info(sessions)")}
    if "profile" not in cols:  # 스킬 상태 코드 (텍스트 없음). 기준 시뮬레이터용
        c.execute("ALTER TABLE sessions ADD COLUMN profile TEXT")
    return c


def init(force: bool = False):
    with _lock, _conn() as c:
        if force:
            c.execute("DELETE FROM companies")
            c.execute("DELETE FROM sessions")
        if c.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
            for tid, data in seed_companies().items():
                c.execute("INSERT INTO companies VALUES (?, ?)", (tid, json.dumps(data, ensure_ascii=False)))


def list_companies() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT data FROM companies ORDER BY tenant_id").fetchall()
    return [json.loads(r[0]) for r in rows]


def get_company(tenant_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT data FROM companies WHERE tenant_id = ?", (tenant_id,)).fetchone()
    return json.loads(row[0]) if row else None


def save_company(data: dict):
    with _lock, _conn() as c:
        c.execute("UPDATE companies SET data = ? WHERE tenant_id = ?",
                  (json.dumps(data, ensure_ascii=False), data["tenant_id"]))


def update_company(tenant_id: str, **fields) -> dict:
    cur = get_company(tenant_id)
    if cur is None:
        raise KeyError(tenant_id)
    cur = deepcopy(cur)
    cur.update(fields)
    save_company(cur)
    return cur


def log_session(company: str, gaps: list[str], profile: dict[str, str] | None = None):
    """익명 기록: 기업 ID, 갭 스킬 ID, 스킬별 상태 코드(own/part/verify)만. 이력서 문장·근거는 저장하지 않는다."""
    allowed = {"own", "part", "verify"}
    prof = {k: v for k, v in (profile or {}).items() if v in allowed}
    with _lock, _conn() as c:
        c.execute("INSERT INTO sessions (company, gaps, created, profile) VALUES (?, ?, ?, ?)",
                  (company, json.dumps(gaps), datetime.now(timezone.utc).isoformat(), json.dumps(prof)))


def sessions_for(company: str) -> list[list[str]]:
    with _conn() as c:
        rows = c.execute("SELECT gaps FROM sessions WHERE company = ?", (company,)).fetchall()
    return [json.loads(r[0]) for r in rows]


def profiles_for(company: str) -> list[dict[str, str]]:
    with _conn() as c:
        rows = c.execute("SELECT profile FROM sessions WHERE company = ? AND profile IS NOT NULL", (company,)).fetchall()
    return [json.loads(r[0]) for r in rows]
