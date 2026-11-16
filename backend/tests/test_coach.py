"""학습 코치 에이전트: 도구 호출, 과정 인용 검증, tenant 고정, 가짜 Bedrock 루프."""
from app.pipeline import coach


def _statuses(client, persona="t1", company="A"):
    r = client.post("/api/diagnose", json={"company_id": company, "persona_id": persona}).json()
    return {s["skill_id"]: s["status"] for s in r["skills_found"]}


def test_coach_rules_uses_tools_and_cites_catalog_only(client):
    st = _statuses(client)
    r = client.post("/api/coach", json={"company_id": "A", "question": "뭐부터 공부하면 좋을까요? 과정도 추천해 주세요",
                                        "statuses": st}).json()
    assert r["mode"] == "mock" and r["answer"]
    tools = [c["tool"] for c in r["tool_calls"]]
    assert "get_company_criteria" in tools and "readiness_after" in tools and "search_courses" in tools
    from app.data import courses
    ids = {c["id"] for c in courses()}
    assert all(c["id"] in ids for c in r["courses"])                 # 카탈로그에 있는 과정만
    assert "점" in r["answer"]


def test_coach_market_and_docs_question(client):
    st = _statuses(client)
    r = client.post("/api/coach", json={"company_id": "A", "question": "엣지 AI는 회사에서 실제로 어떤 업무에 쓰고 시장 수요는 어때요?",
                                        "statuses": st}).json()
    tools = [c["tool"] for c in r["tool_calls"]]
    assert "market_stats" in tools and "company_docs" in tools


def test_coach_tenant_is_fixed():
    from app.adapters import storage
    ctx = coach.Ctx(storage.get_company("B"), {})
    out = coach.call_tool(ctx, "company_docs", {"query": "경산 공장 온보딩", "tenant_id": "A"})  # 모델이 회사를 바꾸려 해도
    assert ctx.calls[-1]["args"] == {"query": "경산 공장 온보딩"}      # 허용되지 않은 인자는 버린다
    assert all("경산" not in h["text"] for h in out["results"])        # A사 문서는 안 나온다


def test_coach_rejects_bad_input(client):
    assert client.post("/api/coach", json={"company_id": "ZZ", "question": "?", "statuses": {}}).status_code == 404
    assert client.post("/api/coach", json={"company_id": "A", "question": "", "statuses": {}}).status_code == 422
    assert client.post("/api/coach", json={"company_id": "A", "question": "x" * 301, "statuses": {}}).status_code == 422
    r = client.post("/api/coach", json={"company_id": "A", "question": "뭐부터?", "statuses": {"nope": "own", "python": "WRONG"}})
    assert r.status_code == 200                                        # 잘못된 스킬·상태는 무시


def test_coach_bedrock_loop_with_fake_model(client, monkeypatch):
    """가짜 Converse: 1턴 도구 호출 → 2턴 답변. 지어낸 과정 ID는 지워진다."""
    from app.adapters import bedrock
    st = _statuses(client)
    seen = {}

    def fake_turn(system, messages, tools, **kw):
        if len(messages) == 1:
            assert "A" not in [t["name"] for t in tools] and len(tools) == 5
            return {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "search_courses",
                                                                  "input": {"skill_id": "python"}}}]}
        res = messages[-1]["content"][0]["toolResult"]["content"][0]["json"]
        seen["res"] = res
        real = res["courses"][0]["course_id"] if res["courses"] else "none"
        return {"role": "assistant", "content": [{"text": f"좋아요 [C:{real}] 그리고 [C:FAKE-999]"}]}

    monkeypatch.setattr(bedrock, "mode", lambda: "bedrock")
    monkeypatch.setattr(bedrock, "converse_turn", fake_turn)
    r = coach.run("A", "파이썬 과정?", st)
    assert r["mode"] == "bedrock" and "[C:FAKE-999]" not in r["answer"]
    assert any("과정 인용" in f for f in r["fallbacks"])
    assert [c["tool"] for c in r["tool_calls"]] == ["search_courses"]


def test_coach_bedrock_failure_falls_back_to_rules(client, monkeypatch):
    from app.adapters import bedrock

    def boom(*a, **k):
        raise bedrock.BedrockError("AWS 로그인 만료")

    monkeypatch.setattr(bedrock, "mode", lambda: "bedrock")
    monkeypatch.setattr(bedrock, "converse_turn", boom)
    r = coach.run("A", "뭐부터?", {})
    assert r["mode"] == "rules" and r["answer"] and any("로그인" in f for f in r["fallbacks"])
