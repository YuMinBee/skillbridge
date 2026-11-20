"""저장소. 기업 설정·트랙과 익명 진단 기록만 저장한다 (이력서 원문·개인 식별 정보는 저장하지 않는다).

백엔드
- 로컬: SQLite (STORAGE=sqlite, 기본)
- 배포: DynamoDB (STORAGE=dynamodb, TABLE_NAME). Lambda가 새로 떠도 기업 설정·진단 기록이 유지된다.

방문자 샌드박스
- 공개 주소에서 아무나 기업 기준을 바꾸면 시연이 망가진다. 그래서 요청에 샌드박스 ID(X-Sandbox 헤더)가
  있으면 기업 설정 읽기·쓰기를 그 방문자 사본으로 한다. 원본은 그대로이고, 사본은 24시간 뒤 사라진다.
- 원본 쓰기는 ALLOW_BASE_WRITE일 때만 (로컬 기본 허용, Lambda 기본 금지).
- 익명 진단 기록(갭 스킬 ID·상태 코드)은 공용 집계로 쌓는다.
"""
import itertools
import json
import re
import sqlite3
import threading
import time
import uuid
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone

from .. import config
from ..data import seed_companies

SANDBOX_TTL = 24 * 3600
_SB_RE = re.compile(r"^[A-Za-z0-9_-]{8,40}$")
_sandbox: ContextVar[str | None] = ContextVar("sandbox", default=None)


class BaseWriteForbidden(PermissionError):
    """샌드박스 없이 원본 기업 설정을 바꾸려 할 때 (배포 환경)."""


def valid_sandbox(sb: str | None) -> str | None:
    return sb if sb and _SB_RE.match(sb) else None


def set_sandbox(sb: str | None):
    """요청 단위 샌드박스 ID 지정 (미들웨어가 호출). 형식이 틀리면 원본(None)."""
    return _sandbox.set(valid_sandbox(sb))


def reset_sandbox_token(token):
    _sandbox.reset(token)


def current_sandbox() -> str | None:
    return _sandbox.get()


# ---------------------------------------------------------------- SQLite
class _Sqlite:
    name = "sqlite"

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()

    def conn(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.execute("CREATE TABLE IF NOT EXISTS companies (tenant_id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS sandbox_companies (sb TEXT, tenant_id TEXT, data TEXT NOT NULL, "
                  "created REAL, PRIMARY KEY (sb, tenant_id))")
        c.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT, gaps TEXT, created TEXT)")
        cols = {r[1] for r in c.execute("PRAGMA table_info(sessions)")}
        if "profile" not in cols:  # 스킬 상태 코드 (텍스트 없음). 기준 시뮬레이터용
            c.execute("ALTER TABLE sessions ADD COLUMN profile TEXT")
        return c

    def base_list(self):
        with self.conn() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT data FROM companies ORDER BY tenant_id")]

    def base_put(self, data):
        with self.lock, self.conn() as c:
            c.execute("INSERT OR REPLACE INTO companies VALUES (?, ?)", (data["tenant_id"], json.dumps(data, ensure_ascii=False)))

    def base_clear(self):
        with self.lock, self.conn() as c:
            c.execute("DELETE FROM companies")
            c.execute("DELETE FROM sessions")
            c.execute("DELETE FROM sandbox_companies")

    def sb_list(self, sb):
        cutoff = time.time() - SANDBOX_TTL
        with self.conn() as c:
            return [json.loads(r[0]) for r in c.execute(
                "SELECT data FROM sandbox_companies WHERE sb = ? AND created > ?", (sb, cutoff))]

    def sb_put(self, sb, data):
        now = time.time()
        with self.lock, self.conn() as c:
            c.execute("DELETE FROM sandbox_companies WHERE created <= ?", (now - SANDBOX_TTL,))
            c.execute("INSERT OR REPLACE INTO sandbox_companies VALUES (?, ?, ?, ?)",
                      (sb, data["tenant_id"], json.dumps(data, ensure_ascii=False), now))

    def sb_clear(self, sb):
        with self.lock, self.conn() as c:
            c.execute("DELETE FROM sandbox_companies WHERE sb = ?", (sb,))

    def session_add(self, company, gaps, prof):
        with self.lock, self.conn() as c:
            c.execute("INSERT INTO sessions (company, gaps, created, profile) VALUES (?, ?, ?, ?)",
                      (company, json.dumps(gaps), datetime.now(timezone.utc).isoformat(), json.dumps(prof)))

    def session_rows(self, company):
        with self.conn() as c:
            rows = c.execute("SELECT gaps, profile FROM sessions WHERE company = ? ORDER BY id", (company,)).fetchall()
        return [(json.loads(g), json.loads(p) if p else None) for g, p in rows]


# ---------------------------------------------------------------- DynamoDB
class _Dynamo:
    """단일 테이블 (pk, sk). 기업 원본 pk=COMPANY · 샌드박스 pk=SB#{id} (ttl) · 진단 기록 pk=SESS#{기업}."""
    name = "dynamodb"

    def __init__(self, table, client=None):
        self.table = table
        self._client = client

    @property
    def c(self):
        if self._client is None:
            self._client = config.boto_session().client("dynamodb")
        return self._client

    def _query(self, pk):
        items, start = [], None
        while True:
            kw = {"TableName": self.table, "KeyConditionExpression": "pk = :p",
                  "ExpressionAttributeValues": {":p": {"S": pk}}}
            if start:
                kw["ExclusiveStartKey"] = start
            r = self.c.query(**kw)
            items += r.get("Items", [])
            start = r.get("LastEvaluatedKey")
            if not start:
                return items

    def _put(self, pk, sk, **attrs):
        item = {"pk": {"S": pk}, "sk": {"S": sk}}
        for k, v in attrs.items():
            item[k] = {"N": str(v)} if isinstance(v, (int, float)) else {"S": v}
        self.c.put_item(TableName=self.table, Item=item)

    def _delete_all(self, pk):
        for it in self._query(pk):
            self.c.delete_item(TableName=self.table, Key={"pk": it["pk"], "sk": it["sk"]})

    def base_list(self):
        return sorted((json.loads(i["data"]["S"]) for i in self._query("COMPANY")), key=lambda d: d["tenant_id"])

    def base_put(self, data):
        self._put("COMPANY", data["tenant_id"], data=json.dumps(data, ensure_ascii=False))

    def base_clear(self):
        for d in self.base_list():
            self._delete_all(f"SESS#{d['tenant_id']}")
        self._delete_all("COMPANY")

    def sb_list(self, sb):
        now = time.time()  # TTL 삭제는 지연될 수 있어 읽을 때도 거른다
        return [json.loads(i["data"]["S"]) for i in self._query(f"SB#{sb}") if float(i["ttl"]["N"]) > now]

    def sb_put(self, sb, data):
        self._put(f"SB#{sb}", data["tenant_id"], data=json.dumps(data, ensure_ascii=False), ttl=int(time.time()) + SANDBOX_TTL)

    def sb_clear(self, sb):
        self._delete_all(f"SB#{sb}")

    def session_add(self, company, gaps, prof):
        # 같은 시각(윈도 시계는 약 15ms 단위)에 연달아 저장해도 넣은 순서대로 정렬되게 인스턴스 내 순번을 넣는다
        sk = f"{datetime.now(timezone.utc).isoformat()}#{next(_SEQ):08d}#{uuid.uuid4().hex[:8]}"
        self._put(f"SESS#{company}", sk, gaps=json.dumps(gaps), profile=json.dumps(prof))

    def session_rows(self, company):
        return [(json.loads(i["gaps"]["S"]), json.loads(i["profile"]["S"]) if "profile" in i else None)
                for i in self._query(f"SESS#{company}")]


_backend = None
_SEQ = itertools.count()


def backend():
    global _backend
    if _backend is None:
        _backend = _Dynamo(config.TABLE_NAME) if config.STORAGE == "dynamodb" else _Sqlite(config.DB_PATH)
    return _backend


def use_backend(b):
    """테스트·배포 스크립트용 백엔드 교체."""
    global _backend
    _backend = b


# ---------------------------------------------------------------- 공개 인터페이스
def init(force: bool = False):
    b = backend()
    if force:
        b.base_clear()
    have = {d["tenant_id"] for d in b.base_list()}
    for tid, data in seed_companies().items():  # 새로 추가된 seed 기업만 채운다 (기존 설정은 덮지 않음)
        if tid not in have:
            b.base_put(data)


def list_companies() -> list[dict]:
    b = backend()
    base = {d["tenant_id"]: d for d in b.base_list()}
    sb = current_sandbox()
    if sb:
        base.update({d["tenant_id"]: d for d in b.sb_list(sb) if d["tenant_id"] in base})
    return [base[k] for k in sorted(base)]


def get_company(tenant_id: str) -> dict | None:
    return next((c for c in list_companies() if c["tenant_id"] == tenant_id), None)


def save_company(data: dict):
    sb = current_sandbox()
    if sb:
        backend().sb_put(sb, data)
    elif config.ALLOW_BASE_WRITE:
        backend().base_put(data)
    else:
        raise BaseWriteForbidden("원본 기업 설정은 바꿀 수 없습니다 (방문자 샌드박스에서만 수정)")


def update_company(tenant_id: str, **fields) -> dict:
    cur = get_company(tenant_id)
    if cur is None:
        raise KeyError(tenant_id)
    cur = deepcopy(cur)
    cur.update(fields)
    save_company(cur)
    return cur


def reset() -> str:
    """시연 초기화. 샌드박스면 그 방문자 사본만 지운다. 원본 초기화는 ALLOW_BASE_WRITE일 때만."""
    sb = current_sandbox()
    if sb:
        backend().sb_clear(sb)
        return "sandbox"
    if not config.ALLOW_BASE_WRITE:
        raise BaseWriteForbidden("원본 초기화는 배포 환경에서 막혀 있습니다")
    init(force=True)
    return "base"


def log_session(company: str, gaps: list[str], profile: dict[str, str] | None = None):
    """익명 기록: 기업 ID, 갭 스킬 ID, 스킬별 상태 코드(own/part/verify)만. 이력서 문장·근거는 저장하지 않는다."""
    allowed = {"own", "part", "verify"}
    prof = {k: v for k, v in (profile or {}).items() if v in allowed}
    backend().session_add(company, list(gaps), prof)


def sessions_for(company: str) -> list[list[str]]:
    return [g for g, _ in backend().session_rows(company)]


def profiles_for(company: str) -> list[dict[str, str]]:
    return [p for _, p in backend().session_rows(company) if p is not None]
