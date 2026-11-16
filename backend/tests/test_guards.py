"""공개 배포 대비 가드: 방문자 샌드박스, 원본 쓰기 금지, IP·시간당 상한, DynamoDB 백엔드."""
import json

import pytest

SB1, SB2 = "visitor-aaaa1111", "visitor-bbbb2222"


def _reqs(client, sb=None):
    h = {"X-Sandbox": sb} if sb else {}
    return client.get("/api/companies/A", headers=h).json()["requirements"]


def test_sandbox_isolates_company_edits(client):
    base = _reqs(client)
    new = {k: 1 for k in list(base)[:2]}
    r = client.put("/api/companies/A/requirements", json={"requirements": new}, headers={"X-Sandbox": SB1})
    assert r.status_code == 200
    assert _reqs(client, SB1) == new
    assert _reqs(client) == base            # 원본 그대로
    assert _reqs(client, SB2) == base       # 다른 방문자에게 안 보임
    # 진단도 그 방문자 기준으로 돈다
    d1 = client.post("/api/diagnose", json={"company_id": "A", "persona_id": "t1"}, headers={"X-Sandbox": SB1}).json()
    d0 = client.post("/api/diagnose", json={"company_id": "A", "persona_id": "t1"}).json()
    assert {m["skill_id"] for m in d1["matrix"] if m["weight_work"]} == set(new)   # 실무 기준 = 그 방문자 사본
    assert {m["skill_id"] for m in d0["matrix"] if m["weight_work"]} == set(base)
    # 초기화는 그 방문자 사본만
    assert client.post("/api/reset", headers={"X-Sandbox": SB1}).json()["scope"] == "sandbox"
    assert _reqs(client, SB1) == base


def test_bad_sandbox_id_is_ignored(client):
    from app.adapters import storage
    assert storage.valid_sandbox("../../etc") is None and storage.valid_sandbox("short") is None
    assert storage.valid_sandbox(SB1) == SB1


def test_base_write_forbidden_on_public_deploy(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "ALLOW_BASE_WRITE", False)
    base = _reqs(client)
    r = client.put("/api/companies/A/requirements", json={"requirements": {list(base)[0]: 2}})
    assert r.status_code == 403
    assert client.post("/api/reset").status_code == 403
    assert _reqs(client) == base
    # 샌드박스에서는 된다
    assert client.put("/api/companies/A/requirements", json={"requirements": {list(base)[0]: 2}},
                      headers={"X-Sandbox": SB2}).status_code == 200


def test_limiter_windows():
    from app.guards.limits import Limiter
    now = [0.0]
    lim = Limiter(per_min=2, per_hour=3, clock=lambda: now[0])
    assert [lim.check("1.1.1.1") for _ in range(3)] == ["ok", "ok", "ip"]
    assert lim.check("2.2.2.2") == "ok"          # 다른 IP는 별도
    assert lim.check("3.3.3.3") == "budget"      # 시간당 3회 소진
    now[0] = 61
    assert lim.check("1.1.1.1") == "budget"      # IP 창은 풀렸지만 시간 예산은 아직
    now[0] = 3700
    assert lim.check("1.1.1.1") == "ok"


def test_middleware_429_and_budget_fallback(client, monkeypatch):
    from app.guards import limits
    monkeypatch.setattr(limits, "limiter", limits.Limiter(per_min=1, per_hour=1000))
    body = {"company_id": "A", "persona_id": "t1"}
    assert client.post("/api/diagnose", json=body).status_code == 200
    r = client.post("/api/diagnose", json=body)
    assert r.status_code == 429 and "1분" in r.json()["detail"]
    assert client.get("/api/market?region=dg&job=ai").status_code == 200   # 비용 없는 경로는 제한 없음

    monkeypatch.setattr(limits, "limiter", limits.Limiter(per_min=100, per_hour=0))
    r = client.post("/api/diagnose", json=body).json()
    assert r["mode"] == "mock" and any("상한" in f for f in r["fallbacks"])


def test_costly_paths():
    from app.guards.limits import costly
    assert costly("POST", "/api/diagnose") and costly("POST", "/api/diagnose/pdf") and costly("POST", "/api/coach")
    assert costly("POST", "/api/companies/A/docs") and costly("GET", "/api/companies/A/evidence")
    assert not costly("GET", "/api/market") and not costly("PUT", "/api/companies/A/requirements")


# ---------------------------------------------------------------- DynamoDB 백엔드 (가짜 클라이언트)
class FakeDynamo:
    """put_item / delete_item / query(pk = :p, 페이지 2개씩) 만 흉내낸다."""

    def __init__(self):
        self.items = {}

    def put_item(self, TableName, Item):
        self.items[(Item["pk"]["S"], Item["sk"]["S"])] = json.loads(json.dumps(Item))

    def delete_item(self, TableName, Key):
        self.items.pop((Key["pk"]["S"], Key["sk"]["S"]), None)

    def query(self, TableName, KeyConditionExpression, ExpressionAttributeValues, ExclusiveStartKey=None):
        assert KeyConditionExpression == "pk = :p"
        pk = ExpressionAttributeValues[":p"]["S"]
        rows = [v for (p, s), v in sorted(self.items.items()) if p == pk]
        start = 0
        if ExclusiveStartKey:
            start = next(i for i, v in enumerate(rows) if v["sk"] == ExclusiveStartKey["sk"]) + 1
        page = rows[start:start + 2]
        out = {"Items": page}
        if start + 2 < len(rows):
            out["LastEvaluatedKey"] = {"pk": page[-1]["pk"], "sk": page[-1]["sk"]}
        return out


@pytest.fixture()
def dynamo_storage():
    from app.adapters import storage
    old = storage.backend()
    fake = FakeDynamo()
    storage.use_backend(storage._Dynamo("t", client=fake))
    storage.init()
    yield storage, fake
    storage.use_backend(old)


def test_dynamo_backend_roundtrip(dynamo_storage):
    storage, fake = dynamo_storage
    ids = [c["tenant_id"] for c in storage.list_companies()]
    import json
    from app.data import SEED
    want = sorted(json.loads(p.read_text(encoding="utf-8"))["tenant_id"] for p in (SEED / "companies").glob("*.json"))
    assert sorted(ids) == want and len(ids) > 8                                      # 페이지 넘김 포함
    storage.update_company("B", desc="바뀜")
    assert storage.get_company("B")["desc"] == "바뀜"
    tok = storage.set_sandbox(SB1)
    try:
        storage.update_company("A", desc="샌드박스")
        assert storage.get_company("A")["desc"] == "샌드박스"
        sb_items = [v for (p, _), v in fake.items.items() if p == f"SB#{SB1}"]
        assert sb_items and all("ttl" in v for v in sb_items)        # 24시간 뒤 자동 삭제
    finally:
        storage.reset_sandbox_token(tok)
    assert storage.get_company("A")["desc"] != "샌드박스"
    for i in range(3):
        storage.log_session("A", [f"g{i}"], {"python": "own", "x": "BAD"})
    assert storage.sessions_for("A") == [["g0"], ["g1"], ["g2"]]
    assert storage.profiles_for("A") == [{"python": "own"}] * 3      # 허용 코드만 저장
    storage.init(force=True)
    assert storage.sessions_for("A") == [] and storage.get_company("B")["desc"] != "바뀜"


def test_dynamo_expired_sandbox_is_ignored(dynamo_storage):
    storage, fake = dynamo_storage
    tok = storage.set_sandbox(SB2)
    try:
        storage.update_company("A", desc="만료 예정")
        for (p, s), v in fake.items.items():
            if p == f"SB#{SB2}":
                v["ttl"] = {"N": "1"}                               # TTL 삭제가 늦어져도
        assert storage.get_company("A")["desc"] != "만료 예정"        # 읽을 때 거른다
    finally:
        storage.reset_sandbox_token(tok)


def test_demo_key_gates_bedrock(client, monkeypatch):
    """시연 키가 있으면 공개 방문자는 규칙 엔진, 키를 보낸 요청만 설정된 모드."""
    from app import config
    from app.adapters import bedrock
    monkeypatch.setattr(config, "DEMO_KEY", "demo-secret-123456")
    m = client.get("/api/meta").json()
    assert m["bedrock"] == "mock" and m["public_mock"] is True
    d = client.post("/api/diagnose", json={"company_id": "A", "persona_id": "t1"}).json()
    assert d["mode"] == "mock" and any("공개 방문자" in f for f in d["fallbacks"])
    m = client.get("/api/meta", headers={"X-Demo-Key": "demo-secret-123456"}).json()
    assert m["public_mock"] is False and m["bedrock"] == bedrock.configured_mode()
    assert client.get("/api/meta", headers={"X-Demo-Key": "wrong"}).json()["public_mock"] is True
