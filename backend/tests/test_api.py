def test_market(client):
    r = client.get("/api/market", params={"region": "dg", "job": "ai"}).json()
    assert r["n"] > 0 and r["top"] and r["evidence"]
    assert all(0 <= t["pct"] <= 100 for t in r["top"])


def test_personas_match_demo_statuses(client):
    """데모 HTML의 예시 지원자 상태가 이력서 텍스트 추출로 재현되는지."""
    r = client.post("/api/diagnose", json={"persona_id": "p1", "company_id": "A", "weekly_hours": 15}).json()
    st = {s["skill_id"]: s["status"] for s in r["skills_found"]}
    assert st["python"] == st["pytorch"] == st["computer_vision"] == st["linux"] == "own"
    assert st["docker"] == "verify"
    assert st["aws"] == st["sql"] == st["cpp"] == st["llm"] == "part"
    assert r["readiness"] == 64


def test_corp_change_updates_diagnosis_immediately(client):
    body = {"persona_id": "p1", "company_id": "A", "weekly_hours": 15}
    before = client.post("/api/diagnose", json=body).json()
    reqs = client.get("/api/companies/A").json()["requirements"]
    reqs["edge_ai"] = 0  # 제외
    client.put("/api/companies/A/requirements", json={"requirements": reqs}).raise_for_status()
    after = client.post("/api/diagnose", json=body).json()
    assert after["readiness"] > before["readiness"]
    assert "edge_ai" not in {m["skill_id"] for m in after["matrix"]}


def test_baseline_shows_missed_and_unnecessary(client):
    r = client.post("/api/diagnose", json={"persona_id": "p1", "company_id": "A", "weekly_hours": 15}).json()
    b = r["baseline"]
    assert "엣지 AI" in b["missed"]
    assert b["readiness_posting"] != b["readiness_company"]


def test_trace_and_evidence_citations(client):
    r = client.post("/api/diagnose", json={"persona_id": "p2", "company_id": "B", "weekly_hours": 15}).json()
    assert len(r["trace"]) >= 8
    for st in r["path"]["steps"]:
        assert st["evidence_ids"] and all(e in r["evidence"] for e in st["evidence_ids"])


def test_reject_unknown_skill_and_empty(client):
    assert client.put("/api/companies/A/requirements", json={"requirements": {"nope": 2}}).status_code == 400
    assert client.put("/api/companies/A/requirements", json={"requirements": {"python": 0}}).status_code == 400
    assert client.post("/api/diagnose", json={"resume_text": "  ", "company_id": "A"}).status_code == 400
    assert client.post("/api/diagnose", json={"resume_text": "Python", "company_id": "Z"}).status_code == 404


def test_tracks_and_doc_suggestions(client):
    t = {"tracks": [{"skills": ["terraform"], "title": "새 트랙", "hours": 5, "benefit": ""}]}
    r = client.put("/api/companies/B/tracks", json=t).json()
    assert r["tracks"][0]["title"] == "새 트랙"
    s = client.post("/api/companies/B/docs", json={"text": "Terraform과 Terraform, Prometheus"}).json()
    top = s["suggestions"][0]
    assert top["skill_id"] == "terraform" and top["suggested_weight"] == 2


def test_insights_anonymous(client):
    r = client.get("/api/companies/A/insights").json()
    assert r["sessions"] > 0 and r["blocked"] and r["vs_market"]


def test_reset(client):
    client.put("/api/companies/A/requirements", json={"requirements": {"python": 2}})
    client.post("/api/reset")
    assert len(client.get("/api/companies/A").json()["requirements"]) > 1


def test_simulator_levers_and_tracks(client):
    r = client.post("/api/companies/B/simulate", json={}).json()
    assert r["n"] > 0 and r["current"]["share"] == r["scenario"]["share"]
    assert sum(r["current"]["hist"]) == r["n"]
    # 필수 하나를 우대로 낮추면 지원 가능 비율은 줄지 않는다
    req = client.get("/api/companies/B").json()["requirements"]
    sid = next(k for k, w in req.items() if w == 2)
    r2 = client.post("/api/companies/B/simulate", json={"requirements": {**req, sid: 1}}).json()
    assert r2["scenario"]["share"] >= r2["current"]["share"]
    # 트랙 이수 가정은 기준이 같아도 비율을 올리거나 유지
    r3 = client.post("/api/companies/B/simulate", json={"assume_tracks": True}).json()
    assert r3["scenario"]["share"] >= r3["current"]["share"] and r3["tracks_effect"]["delta_pp"] >= 0
    # 시뮬레이션은 저장하지 않는다
    assert client.get("/api/companies/B").json()["requirements"] == req
    assert client.post("/api/companies/B/simulate", json={"requirements": {"nope": 2}}).status_code == 400


def test_session_log_keeps_only_status_codes(client):
    from app.adapters import storage
    client.post("/api/diagnose", json={"company_id": "C", "persona_id": "p3"})
    profs = storage.profiles_for("C")
    assert profs and all(set(p.values()) <= {"own", "part", "verify"} for p in profs)


def test_supply_endpoint(client):
    r = client.get("/api/supply?region=dg&job=cloud").json()
    if not r["available"]:
        return
    assert r["points"] and all(p["status"] in ("있음", "원격만", "공백") for p in r["points"])
    assert all((p["seats"] > 0) == (p["status"] == "있음") for p in r["points"])
    assert client.get("/api/supply?region=zz").status_code == 400


def test_path_puts_apply_tier_before_work_tier(client):
    """공고(지원 기준) 갭을 먼저, 기업 실무 기준 갭을 나중에. 공고에만 있는 스킬도 경로에 들어간다."""
    r = client.post("/api/diagnose", json={"company_id": "A", "persona_id": "p1"}).json()
    tiers = [s["tier"] for s in r["path"]["steps"]]
    assert tiers == sorted(tiers, key=lambda t: t != "apply")          # apply가 전부 앞
    preq = {p["skill_id"] for p in r["baseline"]["posting_requirements"]}
    assert all(s["skill_id"] in preq for s in r["path"]["steps"] if s["tier"] == "apply")
    assert 0 <= r["readiness_apply"] <= 100 and r["readiness_apply"] == r["baseline"]["readiness_posting"]
    assert {m["tier"] for m in r["matrix"]} <= {"apply", "work"}
