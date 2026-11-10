"""역량다리 API. 로컬: uvicorn app.main:app --reload (backend/ 에서). Lambda: handler (Mangum)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .adapters import bedrock, storage
from .routers import corp, diagnose, market


@asynccontextmanager
async def lifespan(_app):
    storage.init()
    yield


app = FastAPI(title="역량다리 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(market.router)
app.include_router(diagnose.router)
app.include_router(corp.router)


@app.get("/api/meta")
def meta():
    from .data import courses_source, market_source
    return {"bedrock": bedrock.mode(), "bedrock_mock_env": config.BEDROCK_MOCK, "data_mode": config.DATA_MODE,
            "sources": {"courses": courses_source(), "market": market_source()},
            "region": config.AWS_REGION, "profile": config.AWS_PROFILE, "version": app.version}


@app.post("/api/reset")
def reset():
    """시연 초기화: 기업 설정을 seed로 되돌리고 실제 진단 기록을 지운다."""
    storage.init(force=True)
    return {"ok": True}


# 빌드된 프런트(frontend/dist)가 있으면 같은 주소에서 서빙한다 → Lambda 함수 URL 하나로 시연 가능
_DIST = config.ROOT / "frontend" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")

try:
    from mangum import Mangum

    handler = Mangum(app)
except ImportError:  # 로컬 실행에는 필요 없음
    handler = None
