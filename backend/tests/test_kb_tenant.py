"""M4 완료 조건: 다른 tenant의 문서가 검색되지 않는다."""
import pytest

from app.adapters import kb


class FakeKB:
    """Bedrock retrieve 응답을 흉내 낸다. 필터를 무시하고 모든 tenant 문서를 돌려주는 '고장 난' KB."""

    def __init__(self):
        self.calls = []

    def retrieve(self, **kw):
        self.calls.append(kw)
        docs = [("A", "경산 공장 2라인 온보딩"), ("B", "Grafana 경보 온콜"), ("C", "RAG 회귀 평가")]
        return {"retrievalResults": [
            {"content": {"text": t}, "score": 0.5, "metadata": {"tenantId": tid},
             "location": {"s3Location": {"uri": f"s3://b/corp-docs/{tid}/x.md"}}} for tid, t in docs]}


def test_filter_is_always_injected_server_side(monkeypatch):
    monkeypatch.setattr(kb, "KB_ID", "KBTEST")
    fake = FakeKB()
    kb.retrieve("B", "온콜", client=fake)
    flt = fake.calls[0]["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"]
    assert flt == {"equals": {"key": "tenantId", "value": "B"}}


def test_other_tenant_results_are_dropped_even_if_kb_misbehaves(monkeypatch):
    monkeypatch.setattr(kb, "KB_ID", "KBTEST")
    out = kb.retrieve("B", "온콜", client=FakeKB())
    assert out and all(r["tenant"] == "B" for r in out)


@pytest.mark.parametrize("bad", ["", "A' OR 1=1", "../A", "A" * 40])
def test_bad_tenant_ids_rejected(bad):
    with pytest.raises(kb.TenantError):
        kb.tenant_filter(bad)


def test_local_fallback_stays_in_tenant():
    # A사 고유 문구(경산 공장)는 B로 검색하면 나오지 않는다
    assert any("경산" in r["text"] for r in kb._local("A", "경산 공장", 5))
    assert not any("경산" in r["text"] for r in kb._local("B", "경산 공장", 5))


def test_evidence_endpoint_rejects_unknown_company(client):
    assert client.get("/api/companies/ZZ/evidence", params={"q": "온콜"}).status_code == 404
    r = client.get("/api/companies/B/evidence", params={"q": "Grafana 경보"})
    assert r.status_code == 200 and all(x["tenant"] == "B" for x in r.json()["results"])
