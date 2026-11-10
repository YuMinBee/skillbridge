"""데이터 로더. DATA_MODE=sample이면 seed/의 가상 데이터, live면 collectors/가 만든 공공데이터 정제본을 쓴다.
live 파일이 없으면 샘플로 동작한다."""
import json
from functools import lru_cache

from .config import DATA_MODE, SEED


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=1)
def personas() -> list[dict]:
    return _read_json(SEED / "personas" / "personas.json")


LIVE_COURSES = SEED / "courses" / "live_courses.json"


def courses_source() -> str:
    return "live" if DATA_MODE == "live" and LIVE_COURSES.exists() else "sample"


@lru_cache(maxsize=1)
def courses() -> list[dict]:
    if courses_source() == "live":
        return _read_json(LIVE_COURSES)["courses"]
    return _read_json(SEED / "courses" / "public_courses.json")["courses"]


@lru_cache(maxsize=1)
def seed_companies() -> dict[str, dict]:
    out = {}
    for p in sorted((SEED / "companies").glob("*.json")):
        c = _read_json(p)
        out[c["tenant_id"]] = c
    return out


LIVE_POSTINGS = SEED / "market" / "postings_live.jsonl"


def market_source() -> str:
    """live: 실제 공고 + 샘플 보충(C안), sample: 가상 공고만"""
    return "live" if DATA_MODE == "live" and LIVE_POSTINGS.exists() else "sample"


@lru_cache(maxsize=1)
def market_postings() -> list[dict]:
    rows = _read_jsonl(SEED / "market" / "postings_sample.jsonl")
    if market_source() == "live":
        rows = _read_jsonl(LIVE_POSTINGS) + rows
    return rows


@lru_cache(maxsize=1)
def fake_sessions() -> list[dict]:
    return _read_jsonl(SEED / "sessions" / "fake_sessions.jsonl")
