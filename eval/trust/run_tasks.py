"""과제 구체화 · 교육 추천 거부를 시연 외 자소서로 확인 (2026-11-20).

입력: task_essays/essays.jsonl(합성 자소서 4개, Claude 작성 — 우리에게 유리할 수 있다는 한계) + 시연 자소서.
측정(실제 Bedrock, 파이프라인 전체):
- 과제 구체화: 요청 수 · 원문 대조 통과 수 · 거부 이유
- 교육 추천: 과정 붙음 / 맞는 과정 없음(유사도 기준 미만) / 과정 안 붙이는 역량(소프트·검증 필요)
출력: results_tasks.json (과제 문장과 근거 그대로 — 사람이 읽고 적절한지 따로 본다)
실행: BEDROCK_MOCK=0 python eval/trust/run_tasks.py
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    from app.agents import supervisor as sv
    rows = [json.loads(x) for x in (HERE / "task_essays" / "essays.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    demo = (ROOT / "docs" / "pivot" / "captures" / "demo_resume.md").read_text(encoding="utf-8").split("---", 1)[1].strip()
    rows.insert(0, {"id": "demo", "sector": "private", "family": "auto", "note": "시연 자소서", "text": demo})
    out, tot = [], {"asked": 0, "accepted": 0, "course": 0, "abstain": 0, "no_course": 0, "usd": 0.0}
    for r in rows:
        o = sv.run({"resume": r["text"], "job_family": r["family"], "sector": r["sector"]})
        rec = next(p for p in o["progress"] if p["agent"] == "recommend")
        recos = o["result"]["recommendations"]
        c = sum(1 for x in recos if x.get("course"))
        a = sum(1 for x in recos if x.get("course_note"))
        n = sum(1 for x in recos if not x.get("course") and not x.get("course_note") and not str(x.get("target", "")).startswith("star:"))
        tot["asked"] += rec.get("tasks_asked", 0); tot["accepted"] += rec.get("tasks_accepted", 0)
        tot["course"] += c; tot["abstain"] += a; tot["no_course"] += n; tot["usd"] += o["cost"]["usd"]
        out.append({"id": r["id"], "note": r["note"], "family": o["result"]["job_family"]["label"], "sector": r["sector"],
                    "tasks_asked": rec.get("tasks_asked"), "tasks_accepted": rec.get("tasks_accepted"), "tasks_rejected": rec.get("tasks_rejected"),
                    "recos": [{"target": x["target"], "task": x["task"], "via": x.get("task_via", "template"), "basis": x.get("task_basis"),
                               "course": (x.get("course") or {}).get("name"), "course_note": x.get("course_note")} for x in recos],
                    "verify_passed": o["verify"]["passed"], "usd": o["cost"]["usd"]})
        print(f"{r['id']:10s} {o['result']['job_family']['label']:6s} 과제 {rec.get('tasks_accepted')}/{rec.get('tasks_asked')} "
              f"거부 {rec.get('tasks_rejected')} · 과정 {c} · 맞는 과정 없음 {a} · ${o['cost']['usd']:.3f}")
    tot["usd"] = round(tot["usd"], 3)
    (HERE / "results_tasks.json").write_text(json.dumps({"total": tot, "runs": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("합계", tot)


if __name__ == "__main__":
    main()
