"""역량다리 API. 로컬: uvicorn app.main:app --reload (backend/ 에서). Lambda: handler (Mangum)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .adapters import bedrock, storage
from .guards.limits import GuardMiddleware
from .routers import analyze, coach, corp, diagnose, market


@asynccontextmanager
async def lifespan(_app):
    storage.init()
    yield


app = FastAPI(title="역량다리 API", version="0.2.0", lifespan=lifespan)
app.add_middleware(GuardMiddleware)  # 샌드박스 · IP 상한 · 시간당 Bedrock 상한
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(market.router)
app.include_router(diagnose.router)
app.include_router(corp.router)
app.include_router(coach.router)
app.include_router(analyze.router)


@app.exception_handler(storage.BaseWriteForbidden)
async def _forbidden(_req: Request, e: storage.BaseWriteForbidden):
    return JSONResponse({"detail": str(e)}, status_code=403)


@app.get("/api/meta")
def meta():
    from .data import courses_source, market_source
    return {"bedrock": "mock" if bedrock.forced_reason() else bedrock.configured_mode(),
            "public_mock": bool(config.DEMO_KEY) and bedrock.forced_reason() is not None, "bedrock_mock_env": config.BEDROCK_MOCK, "data_mode": config.DATA_MODE,
            "sources": {"courses": courses_source(), "market": market_source()},
            "storage": storage.backend().name, "sandbox": storage.current_sandbox() is not None,
            "limits": {"per_ip_per_min": config.RATE_PER_MIN, "bedrock_per_hour": config.BEDROCK_PER_HOUR},
            "region": config.AWS_REGION, "profile": config.AWS_PROFILE, "version": app.version}


@app.post("/api/reset")
def reset():
    """시연 초기화. 방문자 샌드박스면 그 사본만 지우고, 원본 초기화는 로컬(ALLOW_BASE_WRITE)에서만."""
    return {"ok": True, "scope": storage.reset()}


# 빌드된 프런트(frontend/dist)가 있으면 같은 주소에서 서빙한다 → Lambda 함수 URL 하나로 시연 가능
_DIST = config.ROOT / "frontend" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")

try:
    from mangum import Mangum

    _mangum = Mangum(app)

    def handler(event, context):
        # Lambda 자기 비동기 호출(adapters/jobs.submit)로 들어온 작업은 HTTP가 아니라 여기서 바로 실행한다
        if isinstance(event, dict) and "skillbridge_job" in event:
            from .adapters import jobs
            storage.init()
            jobs.run(event["skillbridge_job"], event["payload"])
            return {"ok": True}
        return _mangum(event, context)
except ImportError:  # 로컬 실행에는 필요 없음
    handler = None
