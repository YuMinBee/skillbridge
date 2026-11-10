"""요청 단위 가드 (순수 ASGI 미들웨어).

1. 방문자 샌드박스: X-Sandbox 헤더 → storage 컨텍스트. 기업 설정은 방문자 사본으로 읽고 쓴다.
2. IP당 분당 요청 상한 (Bedrock을 부르는 경로만): 넘으면 429.
3. 인스턴스당 시간당 Bedrock 요청 상한: 넘으면 그 요청은 규칙 엔진으로 돈다 (화면에 폴백 사유 표시).
   Lambda 동시 실행 상한(template.yaml)과 곱하면 시간당 최대 호출 수가 정해진다.
"""
import json
import threading
import time
from collections import defaultdict, deque

from .. import config
from ..adapters import bedrock, storage

# Bedrock을 부를 수 있는 경로: POST /api/diagnose*, POST /api/coach, 기업 /docs·/evidence
_COSTLY_SUFFIX = ("/docs", "/evidence")


def costly(method: str, path: str) -> bool:
    if method == "POST" and (path.startswith("/api/diagnose") or path.startswith("/api/coach")):
        return True
    return path.startswith("/api/companies/") and path.endswith(_COSTLY_SUFFIX)


class Limiter:
    def __init__(self, per_min: int, per_hour: int, clock=time.monotonic):
        self.per_min, self.per_hour, self.clock = per_min, per_hour, clock
        self.by_ip: dict[str, deque] = defaultdict(deque)
        self.all: deque = deque()
        self.lock = threading.Lock()

    def check(self, ip: str) -> str:
        """'ok' | 'ip' (IP 상한 → 429) | 'budget' (시간당 상한 → 규칙 엔진)"""
        now = self.clock()
        with self.lock:
            q = self.by_ip[ip]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_min:
                return "ip"
            q.append(now)
            while self.all and now - self.all[0] > 3600:
                self.all.popleft()
            if len(self.all) >= self.per_hour:
                return "budget"
            self.all.append(now)
            if len(self.by_ip) > 5000:  # 메모리 보호
                for k in [k for k, v in self.by_ip.items() if not v][:4000]:
                    del self.by_ip[k]
            return "ok"


limiter = Limiter(config.RATE_PER_MIN, config.BEDROCK_PER_HOUR)


def _header(scope, name: bytes) -> str | None:
    for k, v in scope.get("headers") or []:
        if k == name:
            return v.decode("latin-1")
    return None


def client_ip(scope) -> str:
    xff = _header(scope, b"x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    c = scope.get("client")
    return c[0] if c else "unknown"


class GuardMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        tok_sb = storage.set_sandbox(_header(scope, b"x-sandbox"))
        tok_mock = None
        try:
            if costly(scope["method"], scope["path"]):
                verdict = limiter.check(client_ip(scope))
                if verdict == "ip":
                    body = json.dumps({"detail": "요청이 너무 잦아요. 1분 뒤 다시 시도해 주세요."}, ensure_ascii=False).encode()
                    await send({"type": "http.response.start", "status": 429,
                                "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"retry-after", b"60")]})
                    await send({"type": "http.response.body", "body": body})
                    return
                if verdict == "budget":
                    tok_mock = bedrock.force_mock(f"시간당 Bedrock 호출 상한({config.BEDROCK_PER_HOUR}회) 도달 → 규칙 엔진")
            await self.app(scope, receive, send)
        finally:
            storage.reset_sandbox_token(tok_sb)
            if tok_mock is not None:
                bedrock._force_mock.reset(tok_mock)
