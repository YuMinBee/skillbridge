import os
import sys
import tempfile
from pathlib import Path

# 테스트는 항상 목업·샘플 모드, 임시 DB로 돈다 (app import 전에 설정)
os.environ["BEDROCK_MOCK"] = "1"
os.environ["DATA_MODE"] = "sample"
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["RATE_PER_MIN"] = "10000"  # 상한 자체는 test_guards.py에서 따로 검증
os.environ["STORAGE"] = "sqlite"
os.environ["STAR_CACHE"] = "0"  # 가짜 Bedrock 응답이 테스트끼리 섞이지 않게. 캐시는 test_agents.py에서 따로 검증
os.environ["STAR_CACHE_DIR"] = str(Path(tempfile.mkdtemp()) / "star_cache")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.adapters import storage
    from app.main import app

    storage.init(force=True)
    with TestClient(app) as c:
        yield c
