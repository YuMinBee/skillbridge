"""T1: STAR 강점 진단 · 검증 · 비용 · 작업(job) API (docs/pivot/T1_SUPERVISOR.md 완료 기준)."""
import json

import pytest

from app import config
from app.adapters import bedrock
from app.agents import cost, star, verifier

FULL = ("[프로젝트] 식당 예약 API\n"
        "동아리 행사 예약을 엑셀로 받다 보니 중복 예약이 잦았습니다. 저는 예약 API 설계를 맡았습니다. "
        "Spring Boot로 예약 API를 만들고 동시성 문제를 락으로 막았습니다. 그 결과 중복 예약이 월 12건에서 0건이 되었습니다.")
INFLATED = "[스터디] 데이터 분석\n혁신적으로 스터디를 주도했습니다. 열정적으로 참여했습니다."
RESUME = "이름: 홍길동\n연락처 010-1234-5678\n" + FULL + "\n\n" + INFLATED + "\n[보유기술] Java, Spring Boot, MySQL"


def test_star_full_experience_is_strong():
    (e,), meta = star.diagnose(FULL, use_llm=False)
    assert meta["mode"] == "rule"
    assert all(s["present"] for s in e["slots"].values())
    assert e["slots"]["R"]["quantified"] and e["my_role_clear"]
    assert e["level"] == "strong" and e["score"] == star.MAX_SCORE


def test_star_inflated_words_without_action_are_weak():
    (e,), _ = star.diagnose(INFLATED, use_llm=False)
    assert e["inflated"] and e["level"] == "weak" and e["score"] <= star.INFLATED_CAP


def test_star_skips_skill_and_education_lines():
    exps = star.split_experiences("[학력] OO대학교\n[교육] 부트캠프 6개월 수료\n[보유기술] Java, Docker\n" + FULL)
    assert [e["title"].split(" · ")[0] for e in exps] == ["프로젝트"]


def test_star_llm_quotes_must_exist_in_resume(monkeypatch):
    def fake(system, user, tool, schema, **kw):
        assert tool == "submit_star"
        return {"experiences": [{"title": "예약 API", "text": FULL.split("\n", 1)[1],
                                 "S": "동아리 행사 예약을 엑셀로 받다 보니 중복 예약이 잦았습니다.",
                                 "T": "팀장으로서 전체 일정을 총괄했습니다.",           # 원문에 없음 → 버림
                                 "A": "Spring Boot로 예약 API를 만들고 동시성 문제를 락으로 막았습니다.",
                                 "R": "응답 속도를 80% 개선했습니다."}]}             # 원문에 없음 → 버림
    monkeypatch.setattr(bedrock, "converse_tool", fake)
    (e,), meta = star.diagnose(FULL, use_llm=True)
    assert meta["mode"] == "bedrock" and meta["dropped_quotes"] == 2
    assert e["slots"]["S"]["present"] and e["slots"]["A"]["present"]
    assert not e["slots"]["T"]["present"] and not e["slots"]["R"]["present"]
    assert e["level"] != "strong"  # 지어낸 결과로 점수가 오르지 않는다


def test_star_llm_failure_falls_back_to_rules(monkeypatch):
    def boom(*a, **k):
        raise bedrock.BedrockError("x")
    monkeypatch.setattr(bedrock, "converse_tool", boom)
    res, meta = star.diagnose(FULL, use_llm=True)
    assert meta["mode"] == "rule" and res[0]["level"] == "strong"


def test_star_cache_same_document_same_result(monkeypatch, tmp_path):
    monkeypatch.setenv("STAR_CACHE_DIR", str(tmp_path))
    calls = []

    def fake(system, user, tool, schema, **kw):
        calls.append(1)
        a = "Spring Boot로 예약 API를 만들고 동시성 문제를 락으로 막았습니다." if len(calls) == 1 else None
        return {"experiences": [{"title": "예약 API", "anchor": None,
                                 "S": "동아리 행사 예약을 엑셀로 받다 보니 중복 예약이 잦았습니다.", "T": None, "A": a, "R": None}]}
    monkeypatch.setattr(bedrock, "converse_tool", fake)
    r1, m1 = star.diagnose(FULL, use_llm=True, cache=True)
    r2, m2 = star.diagnose(FULL, use_llm=True, cache=True)
    assert len(calls) == 1 and m1["cached"] is False and m2["cached"] is True
    assert r1 == r2  # 모델이 두 번째에 다르게 답했어도 같은 문서면 같은 결과
    assert FULL not in "".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())  # 원문 전체는 저장 안 함
    r3, _ = star.diagnose(FULL, use_llm=True, cache=False)  # 평가(반복 일치율)는 캐시를 끈다
    assert len(calls) == 2 and not r3[0]["slots"]["A"]["present"]


def test_star_cache_skips_rule_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("STAR_CACHE_DIR", str(tmp_path))

    def boom(*a, **k):
        raise bedrock.BedrockError("x")
    monkeypatch.setattr(bedrock, "converse_tool", boom)
    _, meta = star.diagnose(FULL, use_llm=True, cache=True)
    assert meta["mode"] == "rule" and not list(tmp_path.iterdir())


def test_verifier_drops_fake_course_and_unquoted_evidence():
    result = {"strengths": [], "gaps": [],
              "recommendations": [{"rank": 1, "target": "docker", "course": {"id": "NOPE-1", "name": "없는 과정"},
                                   "cites": [1, 2], "abstained": False}]}
    cites = [{"n": 1, "kind": "resume", "doc_id": "resume", "quote": "이력서에 없는 문장입니다"},
             {"n": 2, "kind": "course", "doc_id": "NOPE-1", "quote": "x"}]
    result, alive, rep = verifier.verify(result, cites, FULL)
    r = result["recommendations"][0]
    assert r["course"] is None and r["abstained"] and alive == []
    assert not rep["passed"]


def test_cost_meter_sums_by_agent():
    log = bedrock.CallLog()
    m = cost.Meter(log, budget=1.0)
    m.start("star"); log.add("star", "global.anthropic.claude-sonnet-4-6", 10, 1000, 200); m.stop("star")
    m.start("recommend"); log.add("x", "global.anthropic.claude-haiku-4-5-20251001-v1:0", 10, 2000, 100); m.stop("recommend")
    s = m.summary()
    assert s["input_tokens"] == 3000 and s["output_tokens"] == 300
    assert abs(s["usd"] - sum(s["by_agent"].values())) < 1e-9
    assert s["by_agent"]["star"] == pytest.approx((1000 * 3 + 200 * 15) / 1e6)
    assert not m.over_budget()


def _run(client, monkeypatch, **body):
    monkeypatch.setenv("JOB_SYNC", "1")
    j = client.post("/api/analyze", json={"resume": RESUME, "job_family": "backend", **body})
    assert j.status_code == 200
    return client.get(f"/api/jobs/{j.json()['job_id']}").json()


def test_analyze_job_end_to_end(client, monkeypatch):
    s = _run(client, monkeypatch)
    assert s["status"] == "done"
    assert [p["agent"] for p in s["progress"]] == ["guard", "star", "skills", "retriever", "recommend", "verifier", "cost"]
    assert all(p["status"] == "done" for p in s["progress"])
    res = s["result"]
    assert {e["level"] for e in res["strengths"]} == {"strong", "weak"}
    assert res["gaps"] and res["recommendations"] and s["verify"]["passed"]
    n_alive = {c["n"] for c in s["citations"]}
    assert all(set(r["cites"]) <= n_alive for r in res["recommendations"])
    assert s["cost"]["usd"] == pytest.approx(sum(s["cost"]["by_agent"].values()))
    dump = json.dumps(s, ensure_ascii=False)
    assert "홍길동" not in dump and "010-1234-5678" not in dump  # 개인정보는 접수 즉시 가린다


def test_analyze_recommends_only_catalog_courses(client, monkeypatch):
    titles = {k: v["title"] for k, v in verifier.course_catalog().items()}  # 기존 카탈로그 + RAG 코퍼스(고용24)
    s = _run(client, monkeypatch)
    for r in s["result"]["recommendations"]:
        if r["course"]:
            assert titles[r["course"]["id"]] == r["course"]["name"]


def test_analyze_budget_exceeded_uses_rules(client, monkeypatch):
    monkeypatch.setattr(config, "JOB_BUDGET_USD", 0.0)
    s = _run(client, monkeypatch)
    assert s["status"] == "done"
    assert any(p.get("note") == "예산 초과 → 규칙 엔진" for p in s["progress"])


def test_analyze_validation(client):
    assert client.post("/api/analyze", json={"resume": RESUME, "job_family": "hardware"}).status_code == 400
    assert client.post("/api/analyze", json={"resume": "짧음", "job_family": "backend"}).status_code == 422
    assert client.get("/api/jobs/j_000000000000").status_code == 404
    assert client.get("/api/jobs/../etc").status_code == 404


def test_template_input_scores_slot_quality(client, monkeypatch):
    monkeypatch.setenv("JOB_SYNC", "1")
    body = {"experiences": [
        {"title": "예약 API", "S": "동아리 예약이 엑셀이라 중복이 잦았습니다", "T": "저는 예약 API 설계를 맡았습니다",
         "A": "Spring Boot로 API를 만들고 락으로 동시성 문제를 막았습니다", "R": "중복 예약이 월 12건에서 0건이 되었습니다"},
        {"title": "스터디", "A": "혁신적으로 스터디를 주도했습니다", "R": "열심히 했습니다 010-1234-5678"}],
        "skills": "Java, Spring Boot"}
    j = client.post("/api/analyze", json=body).json()
    s = client.get(f"/api/jobs/{j['job_id']}").json()
    assert s["status"] == "done"
    a, b = s["result"]["strengths"]
    assert a["level"] == "strong"
    assert b["level"] == "weak" and not b["slots"]["R"]["present"]  # '열심히 했습니다'는 결과가 아니다
    assert "010-1234-5678" not in json.dumps(s, ensure_ascii=False)
    assert s["result"]["job_family"]["inferred"] is True


def test_family_inferred_when_auto(client, monkeypatch):
    s = _run(client, monkeypatch, job_family="auto")
    jf = s["result"]["job_family"]
    assert jf["inferred"] and jf["id"] in ("backend", "ai_ml", "data") and set(jf["scores"]) == {"backend", "ai_ml", "data"}


def test_pdf_rejects_non_pdf(client):
    r = client.post("/api/analyze/pdf", files={"file": ("cv.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_guardrail_midword_address_false_positive_is_undone():
    before = "동아리 행사 예약을 맡았습니다. 주소: 대구 북구 침산로 12. 홍길동님과 협업"
    after = "[주소]리 행사 예약을 맡았습니다. 주소: [주소]. [이름]님과 협업"
    fixed, k = bedrock.undo_midword_address(before, after)
    assert k == 1
    assert fixed.startswith("동아리 행사")          # 단어 중간 오탐은 되돌림
    assert "침산로" not in fixed and "[주소]." in fixed  # 번지 있는 진짜 주소는 그대로 가림
    assert "홍길동" not in fixed                     # 이름은 되돌리지 않음


def test_guardrail_known_false_positive_word_is_undone():
    fixed, k = bedrock.undo_midword_address("동아리 행사를 열었습니다", "[주소] 행사를 열었습니다")
    assert fixed == "동아리 행사를 열었습니다" and k == 1


def test_pdf_requires_essay_or_portfolio(client):
    assert client.post("/api/analyze/pdf", data={"job_family": "auto"}).status_code == 400
    r = client.post("/api/analyze/pdf", files={"essay": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 400


def test_star_llm_experiences_as_json_string(monkeypatch):
    item = {"title": "예약 API", "anchor": None, "S": None, "T": None,
            "A": "Spring Boot로 예약 API를 만들고 동시성 문제를 락으로 막았습니다.", "R": None}
    monkeypatch.setattr(bedrock, "converse_tool", lambda *a, **k: {"experiences": json.dumps([item, "잡음"], ensure_ascii=False)})
    res, meta = star.diagnose(FULL, use_llm=True)
    assert meta["mode"] == "bedrock" and len(res) == 1 and res[0]["slots"]["A"]["present"]


def test_star_salvages_truncated_json_string():
    full = json.dumps([{"title": "a", "A": "x"}, {"title": "b", "A": "y"}], ensure_ascii=False)
    assert [e["title"] for e in star._salvage(full[:-15])] == ["a"]
    assert star._salvage("깨진 문자열") == []


def test_docs_endpoint_reads_markdown_and_rejects_other_types(client, monkeypatch):
    monkeypatch.setenv("JOB_SYNC", "1")
    md = ("# 노션 포트폴리오\n![img](a.png)\n" + FULL).encode()
    r = client.post("/api/analyze/docs", files=[("files", ("notion.md", md, "text/markdown"))])
    assert r.status_code == 200
    s = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert s["status"] == "done" and s["result"]["strengths"][0]["level"] == "strong"
    assert client.post("/api/analyze/docs", files=[("files", ("a.hwp", b"x", "application/octet-stream"))]).status_code == 400
    assert client.post("/api/analyze/docs", data={"github": "not a valid/url/here"}).status_code == 400
    assert client.post("/api/analyze/docs", data={}).status_code == 400


def test_github_readmes_with_fake_api():
    import io as _io
    from app.adapters import github as gh

    class Resp(_io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=10):
        u = req.full_url
        if u.endswith("/repos?per_page=100&sort=pushed"):
            return Resp(json.dumps([{"name": "a", "full_name": "u/a", "fork": False, "private": False, "html_url": "h/a", "description": "d"},
                                    {"name": "f", "full_name": "u/f", "fork": True, "private": False}]).encode())
        if u.endswith("/u/a/readme"):
            return Resp("# A\n<img src=x>\n[링크](http://x)\n```code```\n본문".encode())
        raise OSError("404")
    items = gh.readmes("github.com/u", opener=opener)
    assert [i["repo"] for i in items] == ["a"]  # 포크 제외
    assert "본문" in items[0]["text"] and "<img" not in items[0]["text"] and "code" not in items[0]["text"]
    assert gh.parse("https://github.com/YuMinBee/Coma") == ("YuMinBee", "Coma")


def test_quantified_result_includes_metric_decimals():
    q = star._QUANT
    assert q.search("평가 Macro-F1을 약 0.726에서 0.756으로 높였습니다")
    assert q.search("응답 시간이 820ms에서 140ms로")
    assert not q.search("열심히 노력해 좋은 결과를 얻었습니다")


def test_rag_keyword_search_finds_future_courses():
    from datetime import date
    from app.rag import retrieve as R
    hits = R.search("쿠버네티스", 3, config="bm25", kinds=["course"])
    assert hits and all(h["kind"] == "course" for h in hits)
    assert all(not h["meta"].get("start") or h["meta"]["start"] >= date.today().isoformat() for h in hits)  # 이미 개강한 과정 제외
    assert R.tokens("쿠버네티스 Docker") == ["쿠버", "버네", "네티", "티스", "쿠버네", "버네티", "네티스", "docker"]


def test_sector_changes_requirements_and_is_validated(client, monkeypatch):
    from app.agents import supervisor as S
    pool = {"private": [{"req": {"kubernetes": 2}}], "public": [{"req": {"cert_info_processing": 2}}]}
    assert set(S.pooled_requirements(pool, "private")[0]) == {"kubernetes"}
    assert set(S.pooled_requirements(pool, "public")[0]) == {"cert_info_processing"}  # 섞지 않는다
    s = _run(client, monkeypatch, sector="public")
    assert s["result"]["sector"]["id"] == "public"
    assert client.post("/api/analyze", json={"resume": RESUME, "sector": "both"}).status_code == 400


def test_soft_skill_gap_gets_task_not_course():
    from app.agents import supervisor as sv
    from app.pipeline.family import SOFT
    soft = sorted(SOFT)[0]
    result = {"gaps": [{"id": soft, "name": "커뮤니케이션", "status": "missing", "status_label": "없음", "cites": [1]},
                       {"id": "docker", "name": "Docker", "status": "missing", "status_label": "없음", "cites": [2]}],
              "strengths": []}
    recos = sv._fallback_recommend(result, sv.Cites())
    assert recos[0]["course"] is None and "STAR" in recos[0]["task"]  # IT 과정 코퍼스에서 엉뚱한 과정을 붙이지 않는다
    assert recos[1]["course"] is not None


def test_family_with_few_postings_not_ranked_first(monkeypatch):
    from app.agents import supervisor as sv
    counts = {"backend": 33, "ai_ml": 17, "data": 7}
    monkeypatch.setattr(sv, "family_postings", lambda f, sector="private": counts[f])
    monkeypatch.setattr(sv, "readiness", lambda reqs, st: {"backend": 17, "ai_ml": 15, "data": 26}[reqs["_f"]])
    monkeypatch.setattr(sv, "_pooled", lambda f, sector="private": ({}, {"_f": f}, {}))
    best, scores = sv.infer_family({}, "private")
    assert scores["data"] == 26 and best == "backend"  # 공고 7건 직군은 점수가 높아도 1위로 뽑지 않는다


def test_course_abstains_below_similarity_threshold(monkeypatch):
    from app.agents import supervisor as sv
    from app.rag import retrieve as R
    monkeypatch.setattr(bedrock, "mode", lambda: "bedrock")
    hit = lambda s: [{"doc_id": "W24-X", "title": "누구나 쉽게 접근하는 파이썬", "url": "u", "score": s, "meta": {"start": "2026-12-01"}}]
    monkeypatch.setattr(R, "search", lambda *a, **k: hit(0.343))
    low = sv.find_course("Redis")
    assert low["abstained"] and low["score"] == 0.343
    result = {"gaps": [{"id": "redis", "name": "Redis", "status": "missing", "status_label": "없음", "cites": [1]}], "strengths": []}
    reco = sv._fallback_recommend(result, sv.Cites())[0]
    assert reco["course"] is None and "맞는 과정 없음" in reco["course_note"]  # 옛 카탈로그로 채우지 않는다
    monkeypatch.setattr(R, "search", lambda *a, **k: hit(0.47))
    assert sv.find_course("Docker")["id"] == "W24-X"


def test_task_concretize_keeps_only_grounded_tasks(monkeypatch):
    from app.agents import supervisor as sv, tasks
    resume = "Spring Boot와 MySQL로 대여 API를 만들었습니다. 동아리원 60명이 지금도 씁니다."
    cites = sv.Cites()
    p1 = cites.add("posting", "A 공고", "Docker, CI/CD 등 현대적 개발 환경에 대한 이해 또는 경험")
    p2 = cites.add("posting", "B 공고", "AWS 클라우드 환경에서 백엔드 서비스 설계")
    p3 = cites.add("posting", "C 공고", "Redis 활용 경험")
    gaps = [{"id": "docker", "name": "Docker", "status": "missing", "status_label": "없음", "cites": [p1]},
            {"id": "aws", "name": "AWS", "status": "missing", "status_label": "없음", "cites": [p2]},
            {"id": "redis", "name": "Redis", "status": "missing", "status_label": "없음", "cites": [p3]}]
    recos = [{"rank": i + 1, "target": g["id"], "task": "템플릿", "course": None, "cites": list(g["cites"])} for i, g in enumerate(gaps)]
    monkeypatch.setattr(bedrock, "converse_tool", lambda *a, **k: {"tasks": [
        {"target": "docker", "task": "대여 API를 Docker 이미지로 만들고 실행 방법을 README에 남기기",
         "posting_quote": "Docker, CI/CD 등 현대적 개발 환경", "resume_quote": "Spring Boot와 MySQL로 대여 API를 만들었습니다."},
        {"target": "aws", "task": "응답 시간을 50% 줄이기", "posting_quote": "AWS 클라우드 환경에서 백엔드 서비스 설계", "resume_quote": None},
        {"target": "redis", "task": "캐시 붙이기", "posting_quote": "Redis 대용량 트래픽 처리 경험", "resume_quote": None}]})
    rep = tasks.concretize(recos, gaps, cites.items, resume, cites)
    assert rep["accepted"] == 1 and recos[0]["task"].startswith("대여 API를 Docker") and len(recos[0]["cites"]) == 2
    assert recos[1]["task"] == "템플릿" and recos[2]["task"] == "템플릿"  # 지어낸 숫자 · 공고에 없는 인용 → 템플릿 유지
    assert dict(rep["rejected"]) == {"aws": "원문에 없는 숫자", "redis": "공고 인용이 공고에 없음"}


def test_task_number_check_ignores_tool_names():
    from app.agents.tasks import _numbers_ok
    assert _numbers_ok("JUnit5로 테스트하고 EC2에 배포, k6로 측정해 기록", ["자소서"])
    assert not _numbers_ok("응답 시간을 50% 줄이기", ["자소서"])
    assert _numbers_ok("동아리원 60명이 쓰는 API에 캐시", ["동아리원 60명이 지금도"])


def test_listed_certificate_counts_as_owned():
    from app.agents.supervisor import _cert_status
    m = {"cert_info_processing": {"status": "verify", "evidence": "[자격증] 정보처리기사"},
         "cert_security": {"status": "verify", "evidence": "[자격증] 정보처리기사 필기 합격, 정보보안기사 필기"},
         "java": {"status": "verify", "evidence": "[보유 기술] Java"}}
    _cert_status(m)
    assert m["cert_info_processing"]["status"] == "own" and m["cert_security"]["status"] == "part"
    assert m["java"]["status"] == "verify"  # 기술은 그대로(이름만 있으면 검증 필요)


def test_task_concretize_cached_same_input(monkeypatch, tmp_path):
    from app.agents import supervisor as sv, tasks
    monkeypatch.setenv("STAR_CACHE_DIR", str(tmp_path))
    resume = "Spring Boot로 대여 API를 만들었습니다."
    calls = []

    def fake(*a, **k):
        calls.append(1)
        return {"tasks": [{"target": "docker", "task": f"대여 API를 Docker로 감싸기 {'A' if len(calls) == 1 else 'B'}",
                           "posting_quote": "Docker 경험", "resume_quote": None}]}
    monkeypatch.setattr(bedrock, "converse_tool", fake)

    def once():
        cites = sv.Cites(); n = cites.add("posting", "공고", "Docker 경험")
        gaps = [{"id": "docker", "name": "Docker", "status": "missing", "status_label": "없음", "cites": [n]}]
        recos = [{"rank": 1, "target": "docker", "task": "템플릿", "course": None, "cites": [n]}]
        tasks.concretize(recos, gaps, cites.items, resume, cites, use_cache=True)
        return recos[0]["task"]
    assert once() == once() and len(calls) == 1  # 같은 입력 → 같은 과제


def test_unreadable_pdf_gets_clear_reason(client):
    import io
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(595, 842); b = io.BytesIO(); w.write(b)
    r = client.post("/api/analyze/docs", files=[("files", ("scan.pdf", b.getvalue(), "application/pdf"))], data={"sector": "private"})
    assert r.status_code == 400 and "스캔·이미지 PDF" in r.json()["detail"]


def test_github_only_unreadable_fails_with_reason(monkeypatch):
    from app.adapters import github as gh, jobs
    from app.agents import supervisor as sv
    def boom(*a, **k):
        raise gh.GithubError("GitHub에서 레포를 읽지 못했습니다")
    monkeypatch.setattr(gh, "readmes", boom)
    with pytest.raises(sv.NoInput):
        sv.run({"resume": "", "github": "nobody-zz", "job_family": "auto", "sector": "private"})


def test_radar_six_axes_rule_based():
    """육각형: 축 6개, 요구 비중 최대 축 = 100, 보유하면 그 축 준비도가 오른다(규칙 계산)."""
    from app.agents.supervisor import radar
    reqs = {"java": 2, "spring": 2, "mysql": 1, "aws": 1}
    none = {r["axis"]: r for r in radar(reqs, {}, "backend")}
    have = {r["axis"]: r for r in radar(reqs, {"java": {"status": "own"}, "spring": {"status": "own"}}, "backend")}
    assert len(none) == 6 and max(r["need"] for r in none.values()) == 100
    assert none["언어"]["me"] == 0 and have["언어"]["me"] == 100 and have["프레임워크·API"]["me"] == 100
    assert none["협업·자격"]["me"] is None and none["협업·자격"]["need"] == 0
