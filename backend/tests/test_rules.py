from app.guards.pii import mask
from app.pipeline.extract import extract_posting, extract_resume, judge_status, posting_requirements
from app.pipeline.recommend import build_path
from app.pipeline.score import gaps, readiness
from app.skills import get_dict


def S(**kw):
    return {k: {"status": v, "evidence": "-"} for k, v in kw.items()}


# ── 사전 매칭 ──
def test_alias_longest_match_and_boundaries():
    sd = get_dict()
    ids = [m["skill_id"] for m in sd.find("자바스크립트와 Java, 쿠버네티스(k8s), AWS SageMaker 사용")]
    assert ids == ["javascript", "java", "kubernetes", "kubernetes", "aws_sagemaker"]
    assert [m["skill_id"] for m in sd.find("JavaScript")] == ["javascript"]


def test_short_alias_is_case_sensitive():
    sd = get_dict()
    assert sd.find("sql") == []
    assert [m["skill_id"] for m in sd.find("SQL 튜닝")] == ["sql"]


# ── 점수 ──
def test_readiness_formula():
    reqs = {"python": 2, "docker": 1, "aws": 1}
    assert readiness(reqs, S(python="own", docker="part")) == round((2 + 0.5) / 4 * 100)
    assert readiness(reqs, {}) == 0
    assert readiness({}, S(python="own")) == 0


def test_readiness_is_deterministic():
    reqs = {"python": 2, "pytorch": 2, "sql": 1}
    st = S(python="own", pytorch="verify", sql="part")
    assert len({readiness(reqs, st) for _ in range(20)}) == 1


def test_gap_order_required_first_then_lower_status():
    reqs = {"a_pref_miss": 1, "b_req_part": 2, "c_req_miss": 2, "d_own": 2}
    st = S(b_req_part="part", d_own="own")
    assert [g[0] for g in gaps(reqs, st)] == ["c_req_miss", "b_req_part", "a_pref_miss"]


# ── 이력서 상태 판정 ──
def test_status_rules():
    assert judge_status("PyTorch로 모델을 개발함") == "own"
    assert judge_status("Docker 기초 실습을 수강함") == "part"
    assert judge_status("프로젝트에서 짧게 실습") == "part"  # 약한 근거가 우선
    assert judge_status("[보유기술] Docker") == "verify"


def test_extract_resume_keeps_strongest_evidence():
    r = extract_resume("Python 수업 수강\nPython으로 API 서버를 구축함\n[보유기술] Docker")
    assert r["python"]["status"] == "own"
    assert "구축" in r["python"]["evidence"]
    assert r["docker"]["status"] == "verify"


# ── 공고 ──
def test_posting_sections():
    text = "담당업무\n- 모델 개발\n자격요건\n- Python 활용\n우대사항\n- Docker 경험\n- Python 심화"
    reqs = posting_requirements(text)
    assert reqs == {"python": 2, "docker": 1}
    ev = {m["skill_id"]: m for m in extract_posting(text)}
    assert ev["docker"]["section"] == "우대사항"


# ── 학습경로 ──
COMPANY = {"region": "대경권", "tracks": [{"id": "T1", "skills": ["edge_ai"], "title": "엣지 트랙", "hours": 16, "benefit": ""}]}


def test_path_public_then_corp_and_proof_for_verify():
    reqs = {"edge_ai": 2, "docker": 1}
    p = build_path(reqs, S(docker="verify"), COMPANY, weekly_hours=10)
    kinds = [(s["skill_id"], s["kind"]) for s in p["steps"]]
    assert kinds == [("edge_ai", "public"), ("edge_ai", "corp"), ("docker", "proof")]
    assert p["total_hours"] == sum(s["hours"] for s in p["steps"])
    assert p["weeks"] == -(-p["total_hours"] // 10)


def test_part_with_track_skips_public_course():
    p = build_path({"edge_ai": 2}, S(edge_ai="part"), COMPANY, weekly_hours=10)
    assert [s["kind"] for s in p["steps"]] == ["corp"]


def test_path_never_invents_courses():
    from app.data import courses
    ids = {c["id"] for c in courses()}
    p = build_path({"jax": 2, "python": 2}, {}, {"region": "전국", "tracks": []}, 10)
    for s in p["steps"]:
        if s["kind"] == "public":
            assert s["course_id"] in ids
    assert any(s["kind"] == "self" and s["skill_id"] == "jax" for s in p["steps"])


def test_market_generator_duty_lines_have_no_skills():
    """가상 공고의 담당업무 문구가 스킬로 잡히면 언급률이 부풀려진다."""
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "scripts" / "gen_market_sample.py"
    spec = importlib.util.spec_from_file_location("gen", p)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    sd = get_dict()
    for lines in gen.DUTY.values():
        for line in lines:
            assert sd.find(line) == [], line


def test_pii_mask():
    t, n = mask("이름: 홍길동\n연락처 010-1234-5678, hong@example.com")
    assert "홍길동" not in t and "010-1234-5678" not in t and "hong@example.com" not in t
    assert n == 3


def test_long_courses_never_inflate_path(monkeypatch):
    from app.pipeline import recommend
    cat = [{"id": "L1", "title": "장기 과정", "provider": "x", "hours": 960, "skills": ["ros"], "level": "실무", "region": "대경권"}]
    monkeypatch.setattr(recommend, "courses", lambda: cat)
    with_track = {"region": "대경권", "tracks": [{"id": "T", "skills": ["ros"], "title": "트랙", "hours": 8, "benefit": ""}]}
    p = build_path({"ros": 1}, {}, with_track, 10)
    assert [s["kind"] for s in p["steps"]] == ["corp"] and p["total_hours"] == 8
    p = build_path({"ros": 1}, {}, {"region": "대경권", "tracks": []}, 10)
    assert p["steps"][0]["kind"] == "self" and p["steps"][0]["ref_course_id"] == "L1"
    assert p["total_hours"] == recommend.SELF_STUDY_HOURS


def test_live_catalog_is_well_formed():
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parents[2] / "seed" / "courses" / "live_courses.json"
    if not f.exists():
        return
    sd = get_dict()
    cs = json.loads(f.read_text(encoding="utf-8"))["courses"]
    assert cs and len({c["id"] for c in cs}) == len(cs)
    for c in cs:
        assert c["hours"] > 0 and c["skills"] and all(sd.exists(s) for s in c["skills"])
        assert c["region"] in ("대경권", "수도권", "기타", "전국")
        assert not any(k.startswith("trprChap") for k in c)  # 담당자 정보 저장 안 함


def test_optimizer_keeps_steps_and_skill_order():
    from app.pipeline.recommend import optimize_order
    reqs = {"edge_ai": 2, "docker": 1, "ros": 1}
    path = build_path(reqs, S(docker="verify"), COMPANY, 10)
    postings = [{"docker": 2, "python": 2}, {"edge_ai": 2}, {"ros": 1, "docker": 2}]
    opt = optimize_order(path, S(docker="verify"), reqs, postings)
    assert sorted(id(s) for s in opt["steps"]) == sorted(id(s) for s in path["steps"])
    kinds = [s["kind"] for s in opt["steps"] if s["skill_id"] == "edge_ai"]
    assert kinds == ["public", "corp"]  # 같은 스킬 안 순서 유지
    after = [s["gain"]["readiness_after"] for s in opt["steps"]]
    assert after == sorted(after) and all(s["gain"]["readiness"] >= 0 for s in opt["steps"])
    # 기업 트랙 없이 공공 과정만 있는 스킬(ros)은 '부분'까지만 올라 100점이 아닐 수 있다
    assert after[-1] <= 100
    assert opt["market"]["fit_after"] >= opt["market"]["fit_before"]
