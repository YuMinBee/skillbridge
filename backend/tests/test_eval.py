"""M5 평가 스크립트가 오프라인에서 끝까지 돌고, 정답셋 형식이 맞는지."""
import json
import subprocess
import sys

from app.config import ROOT
from app.skills import get_dict

EV = ROOT / "eval"


def _jl(name):
    return [json.loads(l) for l in open(EV / name, encoding="utf-8") if l.strip()]


def test_gold_labels_use_dictionary_ids():
    ids = set(get_dict().skills)
    for r in _jl("gold_postings.jsonl"):
        assert set(r["labels"]) <= ids, r["id"]
        assert set(r["labels"].values()) <= {"required", "preferred"}
    for g in _jl("gold_courses.jsonl"):
        assert g["skill_id"] in ids
        assert set(g["relevance"].values()) <= {0, 1, 2}


def test_synthetic_candidates_cover_company_requirements():
    for c in _jl("synthetic_candidates.jsonl"):
        reqs = json.loads((ROOT / f"seed/companies/{c['company']}.json").read_text(encoding="utf-8"))["requirements"]
        assert set(c["gold_status"]) == set(reqs)
        for sid, st in c["gold_status"].items():
            assert st in {"own", "part", "verify", "miss"}
            assert (sid in c["variants"]) == (st != "miss")


def test_run_eval_offline_writes_report():
    r = subprocess.run([sys.executable, str(EV / "run_eval.py")], capture_output=True, text=True, encoding="utf-8",
                       timeout=300, cwd=ROOT, env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stderr[-800:]
    res = json.loads((EV / "results.json").read_text(encoding="utf-8"))
    d = next(x for x in res["postings"]["rows"] if x["stage"] == "dict")
    assert 0 < d["f1"] <= 1
    assert res["baseline"]["agg"]["company"]["gap_cov"] >= res["baseline"]["agg"]["posting"]["gap_cov"]
    assert "## 4. 공고만 본 추천" in (EV / "report.md").read_text(encoding="utf-8")
