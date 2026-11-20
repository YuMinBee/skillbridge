"""직접 수집한 민간 공고(seed/market/direct_it*.jsonl) 검사. 올리기 전에 돌린다.

python scripts/check_direct.py

- 필수 필드, family 값(backend/ai_ml/data), 링크가 중개 사이트가 아닌지
- 파일 사이·파일 안 링크 중복, 공채속보(gongchae_it.jsonl)와 링크 중복
- 한 회사·직군당 2건 초과
- 직군별 합계(서비스가 쓰는 건수)
규칙: seed/market/direct_it.md
"""
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M = ROOT / "seed" / "market"
NEED = ["id", "source", "company", "position", "career", "url", "text", "family", "collected"]
FAMILIES = {"backend", "ai_ml", "data"}
BROKER = re.compile(r"saramin|jobkorea|wanted\.co\.kr|rocketpunch|linkedin|incruit|jobplanet|catch\.co\.kr|linkareer|inthiswork")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def rows(f):
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def main():
    bad = 0
    gc = {(g.get("url") or "").rstrip("/") for g in rows(M / "gongchae_it.jsonl")} if (M / "gongchae_it.jsonl").exists() else set()
    seen, per_co, fam = {}, collections.Counter(), collections.Counter()
    for f in sorted(M.glob("direct_it*.jsonl")):
        for i, d in enumerate(rows(f), 1):
            where = f"{f.name}:{i} {d.get('company', '?')} · {d.get('position', '?')}"
            miss = [k for k in NEED if not d.get(k)]
            u = (d.get("url") or "").rstrip("/")
            errs = []
            if miss:
                errs.append(f"빈 필드 {miss}")
            if d.get("family") not in FAMILIES:
                errs.append(f"family={d.get('family')!r} (backend/ai_ml/data 중 하나)")
            if BROKER.search(u):
                errs.append("중개 사이트 링크 (기업 공식 채용 페이지만)")
            if u in seen:
                errs.append(f"링크 중복: {seen[u]}")
            if u in gc:
                errs.append("공채속보에 이미 있는 공고")
            if "자격요건" not in d.get("text", "") and "지원자격" not in d.get("text", ""):
                errs.append("text에 '자격요건' 문장이 없음")
            seen.setdefault(u, where)
            per_co[(d.get("company"), d.get("family"))] += 1
            fam[d.get("family")] += 1
            if errs:
                bad += 1
                print("✗", where, "→", "; ".join(errs))
    for (co, fa), n in per_co.items():
        if n > 2:
            bad += 1
            print(f"✗ {co} {fa} {n}건 (한 회사·직군당 최대 2건)")
    print(f"\n직접 수집 합계: 백엔드 {fam['backend']} · AI/ML {fam['ai_ml']} · 데이터 {fam['data']} (중복 제외 전)")
    print("문제 없음" if not bad else f"문제 {bad}건 — 고친 뒤 다시 돌리기")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
