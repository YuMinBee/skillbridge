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


def test_interview_company_uses_stated_must_haves_as_apply_tier(client):
    """공고가 없는 현업 청취 기업: '필수'가 지원 기준, 필수+우대가 실무 기준."""
    c = client.get("/api/companies/F").json()
    assert c["apply_requirements"] == {"docker": 2, "networking": 2, "rest_api": 2}
    assert all(not s.get("url") for s in c["sources"].values())
    d = client.post("/api/diagnose", json={"company_id": "F", "resume_text":
                    "Docker로 서비스를 배포하고 운영했습니다. Nginx 리버스 프록시를 구축했습니다."}).json()
    tiers = {m["skill_id"]: m["tier"] for m in d["matrix"]}
    assert tiers["docker"] == tiers["rest_api"] == "apply" and tiers["nginx"] == "work"
    assert any("현업 필수" in s["detail"] for s in d["trace"])


def test_child_skill_implies_parent(client):
    """MySQL로 DB를 설계했으면 'SQL' 필수는 갭이 아니다. 반대 방향(SQL → MySQL)은 인정하지 않는다."""
    from app.pipeline import implies
    m, added = implies.expand({"pytorch": {"status": "own", "evidence": "PyTorch 모델 개발"}})
    assert m["deep_learning"]["status"] == m["machine_learning"]["status"] == "own"
    assert ("deep_learning", "pytorch") in added and "pytorch" in m
    m, _ = implies.expand({"sql": {"status": "own", "evidence": "SQL"}})
    assert "mysql" not in m
    m, _ = implies.expand({"sql": {"status": "own", "evidence": "a"}, "mysql": {"status": "part", "evidence": "b"}})
    assert m["sql"]["evidence"] == "a"                                   # 더 강한 직접 근거 유지
    d = client.post("/api/diagnose", json={"company_id": "G", "resume_text":
                    "MySQL로 쇼핑몰 DB를 설계하고 운영했습니다."}).json()
    row = next(x for x in d["matrix"] if x["skill_id"] == "sql")
    assert row["status"] == "own" and "MySQL 근거로 인정" in row["evidence"]
    assert "sql" not in {g["skill_id"] for g in d["baseline"]["gaps_posting"]}


def test_project_fit_depends_on_department(client):
    """현업: '그 부서에 맞는 경험이었는지'. 같은 이력서라도 게임 부서엔 맞고 서비스 운영 부서엔 안 맞는다."""
    resume = ("[프로젝트]\n- 게임 동아리에서 Unity와 C#으로 모바일 퍼즐 게임을 개발해 스토어에 출시함\n"
              "  UGUI로 인벤토리 화면과 버튼 이벤트를 구현함\n[보유기술] Docker")
    h = client.post("/api/diagnose", json={"company_id": "H", "resume_text": resume}).json()["project_fit"]
    assert h["verdict"] == "fit" and h["mini_project"] is None
    assert "게임" in h["units"][0]["domain"] and {"unity", "csharp", "ugui"} <= {m["skill_id"] for m in h["units"][0]["matched"]}
    f = client.post("/api/diagnose", json={"company_id": "F", "resume_text": resume}).json()
    pf = f["project_fit"]
    assert pf["verdict"] != "fit" and pf["mini_project"]
    assert any("Docker를 활용한 컨테이너" in x["what"] for x in pf["mini_project"]["show"])  # 현업 문항 원문
    assert next(o for o in f["others"] if o["company_id"] == "H")["project_fit"] == h["best_fit"]


def test_project_units_skip_skill_lists():
    from app.pipeline.projectfit import units
    u = units("[보유기술] Docker, Python\n- 졸업작품: 쇼핑몰 백엔드 개발\n  REST API 설계\n[학력] OO대")
    assert u == ["- 졸업작품: 쇼핑몰 백엔드 개발 REST API 설계"]
