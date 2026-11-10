"""M2 완료 조건 확인: BEDROCK_MOCK=0에서 예시 지원자 3명 진단이 끝까지 돌고 trace가 남는지.

실행: python scripts/smoke_bedrock.py   (먼저 aws sso login --profile kosa)
규칙(목업) 결과와 나란히 비교해 출력한다. 진단 기록은 남기지 않는다(log=False).
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "smoke.db")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    os.environ["BEDROCK_MOCK"] = "0"
    from app.adapters import bedrock, storage
    from app.data import personas
    from app.pipeline import diagnose

    assert bedrock.mode() == "bedrock", "BEDROCK_MOCK=0, MODEL_ID 설정 확인"
    storage.init(force=True)
    ok = True
    for p in personas():
        cid = p.get("default_company", "A")
        t0 = time.perf_counter()
        r = diagnose.run(p["resume"], cid, p.get("weekly_hours", 10), log=False)
        dt = time.perf_counter() - t0
        bedrock.BEDROCK_READY = False
        m = diagnose.run(p["resume"], cid, p.get("weekly_hours", 10), log=False)
        bedrock.BEDROCK_READY = True

        print(f"\n=== {p['id']} {p.get('name', '')} → {r['company']['name']} · {dt:.1f}s")
        print(f"준비도  Bedrock {r['readiness']}  /  규칙 {m['readiness']}")
        bs = {x['skill_id']: x['status'] for x in r['skills_found']}
        ms = {x['skill_id']: x['status'] for x in m['skills_found']}
        for sid in sorted(set(bs) | set(ms)):
            if bs.get(sid) != ms.get(sid):
                how = next((x['how'] for x in r['skills_found'] if x['skill_id'] == sid), '-')
                print(f"  차이 {sid:20s} Bedrock={bs.get(sid, '-'):7s} 규칙={ms.get(sid, '-'):7s} ({how})")
        if r["extraction"]:
            print("  추출:", {k: v for k, v in r["extraction"].items()})
        print("  사용량:", r["usage"], "· 폴백:", r["fallbacks"] or "없음")
        for s in r["trace"]:
            calls = ", ".join(f"{c['kind']}:{c['model']} {c['ms']}ms" for c in s.get("calls", []))
            print(f"  [{s['ms']:>7.0f}ms] {s['name']} — {s['detail']}" + (f"  ({calls})" if calls else ""))
        if r["path"]["steps"]:
            print("  설명 예:", r["path"]["steps"][0]["why"])
        ok &= not r["fallbacks"] and len(r["trace"]) == 10
    print("\n결과:", "통과" if ok else "확인 필요")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
