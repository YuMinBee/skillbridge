"""BEDROCK_MOCK=0 경로를 가짜 Bedrock 클라이언트로 검증한다 (AWS 호출 없음).

확인하는 것: 원문에 없는 근거 버림, 후보 밖 스킬 ID 거부, 인용 검증·재생성·템플릿 대체,
trace에 호출 기록, 호출 실패 시 단계별 폴백.
"""
import hashlib
import io
import json

import pytest

from app.adapters import bedrock

RESUME = ("- PyTorch로 객체 탐지 모델을 개발함\n"
          "- 쿠베 기초 강의를 수강함\n"
          "- [보유기술] Docker")


def _vec(text):
    h = hashlib.sha256(text.encode()).digest()
    return [b / 255 for b in h[:16]]


class FakeClient:
    def __init__(self, explain_bad=0, fail=None):
        self.explain_bad = explain_bad  # 앞에서부터 몇 번의 설명 응답을 인용 없이 줄지
        self.fail = fail
        self.calls = []

    def _tool(self, name, data):
        return {"output": {"message": {"content": [{"toolUse": {"name": name, "input": data}}]}},
                "usage": {"inputTokens": 10, "outputTokens": 5}}

    def converse(self, **kw):
        name = kw["toolConfig"]["tools"][0]["toolSpec"]["name"]
        self.calls.append(name)
        if self.fail and self.fail in name:
            raise RuntimeError("boom")
        user = kw["messages"][0]["content"][0]["text"]
        if name == "submit_skills":
            return self._tool(name, {"items": [
                {"mention": "PyTorch", "standard_name": "PyTorch", "evidence": "PyTorch로 객체 탐지 모델을 개발함", "status": "own"},
                {"mention": "쿠베", "standard_name": "Kubernetes", "evidence": "쿠베 기초 강의를 수강함", "status": "part"},
                {"mention": "Spark", "standard_name": "Apache Spark", "evidence": "Spark로 대용량 데이터를 처리함", "status": "own"},  # 지어낸 근거
                {"mention": "젯슨", "standard_name": "", "evidence": "PyTorch로 객체 탐지 모델을 개발함", "status": "own"},
            ]})
        if name == "submit_requirements":
            return self._tool(name, {"items": [
                {"mention": "Python", "standard_name": "Python", "section": "required", "evidence": "Python 활용 능력"},
                {"mention": "PyTorch", "standard_name": "PyTorch", "section": "preferred", "evidence": "PyTorch 사용 경험"},
            ]})
        if name == "submit_links":
            # 첫 후보 밖의 ID를 일부러 고른다 → 거부되어야 함
            return self._tool(name, {"items": [{"i": 0, "skill_id": "not_a_candidate"}]})
        if name == "submit_explanations":
            steps = [int(x.split("]")[0]) for x in user.split("[단계 ")[1:]]
            bad = self.explain_bad > 0
            self.explain_bad -= 1
            items = []
            for i in steps:
                ids = [ln.split()[1] for ln in user.split(f"[단계 {i}]")[1].split("\n[단계")[0].splitlines() if ln.strip().startswith("- E")]
                items.append({"step": i, "why": "근거 없이 쓴 설명" if bad else f"필요한 역량이에요 [{ids[0]}]."})
            return self._tool(name, {"items": items})
        raise AssertionError(name)

    def invoke_model(self, modelId, body):
        if self.fail == "embed":
            raise RuntimeError("boom")
        t = json.loads(body)["inputText"]
        return {"body": io.BytesIO(json.dumps({"embedding": _vec(t)}).encode())}

    def apply_guardrail(self, **kw):
        if self.fail == "guardrail":
            raise RuntimeError("boom")
        t = kw["content"][0]["text"]["text"]
        return {"action": "NONE", "assessments": [], "outputs": [{"text": t}]}


@pytest.fixture()
def fake(monkeypatch):
    from app.pipeline import extract
    from app.pipeline import normalize as norm

    def install(**kw):
        fc = FakeClient(**kw)
        monkeypatch.setattr(bedrock, "client", lambda: fc)
        monkeypatch.setattr(bedrock, "BEDROCK_MOCK", False)
        monkeypatch.setattr(bedrock, "MODEL_ID", "fake-model")
        monkeypatch.setattr(bedrock, "GUARDRAIL_ID", "g-1")
        extract._POSTING_CACHE.clear()
        from app.config import DB_PATH
        (DB_PATH.parent / "posting_cache.json").unlink(missing_ok=True)
        norm.skill_index.cache_clear()
        return fc

    yield install
    norm.skill_index.cache_clear()
    extract._POSTING_CACHE.clear()


def test_resume_extraction_drops_invented_evidence(fake):
    from app.pipeline.extract import extract_resume_llm
    fake()
    res, st = extract_resume_llm(RESUME)
    assert res["pytorch"]["status"] == "own"
    assert res["kubernetes"]["status"] == "part" and res["kubernetes"]["how"] == "dict-std"
    assert "spark" not in res  # 원문에 없는 근거 → 버림
    assert st["dropped"] == 1
    assert res["docker"]["how"] == "dict-rule" and res["docker"]["status"] == "verify"  # 안전망


def test_normalize_rejects_ids_outside_candidates(fake):
    from app.pipeline.normalize import normalize
    fake()
    ms = normalize([{"mention": "젯슨", "evidence": "-"}])
    assert ms[0]["skill_ids"] == [] and ms[0]["how"] == "none"


def _steps():
    ev = {"E1": {"id": "E1", "type": "corp", "text": "필수"}, "E2": {"id": "E2", "type": "market", "text": "30%"}}
    steps = [{"skill": "엣지 AI", "kind": "public", "title": "과정", "hours": 10, "evidence_ids": ["E1", "E2"]}]
    return steps, ev


def test_explain_retries_once_then_passes(fake):
    fc = fake(explain_bad=1)
    steps, ev = _steps()
    whys, n_tpl = bedrock.explain_steps(steps, ev, "회사")
    assert fc.calls.count("submit_explanations") == 2 and n_tpl == 0
    assert bedrock.cites_valid(whys[0], {"E1", "E2"})


def test_explain_falls_back_to_template(fake):
    fake(explain_bad=2)
    steps, ev = _steps()
    whys, n_tpl = bedrock.explain_steps(steps, ev, "회사")
    assert n_tpl == 1 and whys[0] == bedrock.template_why(steps[0], ev)


def test_diagnose_bedrock_mode_records_calls(fake):
    from app.adapters import storage
    from app.pipeline import diagnose
    fake()
    storage.init(force=True)
    r = diagnose.run(RESUME, "A", 10, log=False)
    assert r["mode"] == "bedrock" and r["fallbacks"] == []
    assert len(r["trace"]) == 10
    kinds = {c["kind"] for s in r["trace"] for c in s.get("calls", [])}
    assert {"guardrail", "extract", "explain"} <= kinds
    assert r["usage"]["calls"] >= 4
    assert r["baseline"]["posting_requirements"][0]["skill_id"] == "python"
    for st in r["path"]["steps"]:
        assert bedrock.cites_valid(st["why"], set(st["evidence_ids"]))


@pytest.mark.parametrize("where", ["submit_skills", "submit_explanations", "guardrail", "submit_requirements"])
def test_each_step_falls_back_on_failure(fake, where):
    from app.adapters import storage
    from app.pipeline import diagnose
    fake(fail=where)
    storage.init(force=True)
    r = diagnose.run(RESUME, "A", 10, log=False)
    assert len(r["fallbacks"]) == 1
    assert len(r["trace"]) == 10 and r["readiness"] >= 0
