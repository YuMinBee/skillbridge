"""내 자료로 분석해 보기 (개인 테스트용). 화면에 직접 올리지 않아도 된다.

설정: .env에 경로만 적는다 (개인 자료라 레포에 넣지 않는다. .env와 결과 폴더는 .gitignore에 있음)
    MY_DOCS=C:/.../자소서.docx;C:/.../cv.pdf;C:/.../노션.md     (; 로 여러 개)
    MY_GITHUB=YuMinBee                                          (선택)

실행:  .venv\\Scripts\\python scripts\\try_mine.py            (Bedrock, 약 1분·$0.2)
      .venv\\Scripts\\python scripts\\try_mine.py --mock     (규칙 엔진, 0원)
      .venv\\Scripts\\python scripts\\try_mine.py --family ai_ml
결과:  eval/private/mine_날짜시각.json (전체 결과) + 화면에 요약. 이전 실행과 바뀐 점도 보여 준다.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "private"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="Bedrock 없이 규칙 엔진으로")
    ap.add_argument("--family", default="auto", choices=["auto", "backend", "ai_ml", "data"])
    a = ap.parse_args()
    if a.mock:
        os.environ["BEDROCK_MOCK"] = "1"
    sys.path.insert(0, str(ROOT / "backend"))
    from app import config  # noqa: F401  (.env 읽기)
    from app.adapters import docs
    from app.agents import supervisor
    from app.guards import pii

    paths = [p.strip() for p in os.getenv("MY_DOCS", "").split(";") if p.strip()]
    gh = os.getenv("MY_GITHUB", "").strip()
    if not paths and not gh:
        sys.exit(".env에 MY_DOCS(문서 경로, ; 로 구분) 또는 MY_GITHUB(아이디)를 적어 주세요")
    parts = []
    for p in paths:
        f = Path(p)
        if not f.exists():
            sys.exit(f"파일이 없습니다: {f.name}")
        t = docs.text_of(f.name, f.read_bytes())
        print(f"· {f.name}: {len(t):,}자")
        parts.append(f"[{f.stem}]\n{t}")
    if gh:
        print(f"· GitHub: {gh}")

    t0 = time.time()
    out = supervisor.run({"resume": pii.mask("\n\n".join(parts))[0], "github": gh, "job_family": a.family})
    sec = time.time() - t0
    r = out["result"]

    print(f"\n{sec:.0f}초 · ${out['cost']['usd']:.3f} · 모드 {next((p.get('mode') for p in out['progress'] if p['agent'] == 'star'), '')}")
    fails = [f"{p['agent']}: {p.get('note')}" for p in out["progress"] if p["status"] == "failed" or p.get("note")]
    if fails:
        print("주의:", " / ".join(fails))
    print("\n강점 직군:", " > ".join(f"{x['label']} {x['score']}" for x in r["job_family"]["ranking"]))
    print("\n① 경험 (STAR)")
    for e in r["strengths"]:
        slots = "".join(k if v["present"] else "·" for k, v in e["slots"].items())
        print(f"  [{slots}] {e['level']:6} {e['score']:>3} {e['title'][:40]}" + (f"  → {e['missing_hint']}" if e["missing_hint"] else ""))
    print("\n② 부족한 역량:", ", ".join(f"{g['name']}({g['status_label']})" for g in r["gaps"][:10]) or "없음")
    print("\n③ 추천")
    for x in r["recommendations"]:
        c = f"  [과정] {x['course']['name']}" if x.get("course") else ""
        print(f"  {x['rank']}. {x.get('task') or x.get('abstain_reason')}{c}")
    print(f"\n검증: {'통과' if out['verify']['passed'] else '제거 ' + str(len(out['verify']['removed'])) + '건'}")

    OUT.mkdir(parents=True, exist_ok=True)
    prev = sorted(OUT.glob("mine_*.json"))
    path = OUT / f"mine_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps({"sec": round(sec, 1), **out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: eval/private/{path.name}")
    if prev:  # 지난번과 비교: 코드를 고친 뒤 결과가 어떻게 바뀌었는지
        old = json.loads(prev[-1].read_text(encoding="utf-8"))
        lv = lambda o: [(e["title"][:20], e["level"]) for e in o["result"]["strengths"]]  # noqa: E731
        print(f"지난번({prev[-1].name}) 대비: 경험 {len(old['result']['strengths'])}→{len(r['strengths'])}개, "
              f"비용 ${old['cost']['usd']:.3f}→${out['cost']['usd']:.3f}, 1위 직군 "
              f"{old['result']['job_family']['ranking'][0]['label']}→{r['job_family']['ranking'][0]['label']}"
              + ("" if lv(old) == lv(out) else " · 강점 판정 바뀜"))


if __name__ == "__main__":
    main()
