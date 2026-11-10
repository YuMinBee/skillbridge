import os
import sys
import tempfile
from pathlib import Path

# 테스트는 항상 목업·샘플 모드, 임시 DB로 돈다 (app import 전에 설정)
os.environ["BEDROCK_MOCK"] = "1"
os.environ["DATA_MODE"] = "sample"
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
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
