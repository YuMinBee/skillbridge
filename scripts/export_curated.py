"""시장 공고 → S3 curated/ 적재용 JSONL (Athena 테이블 postings, posting_skills).

로컬에 backend/.data/curated/ 로 쓴다. 업로드는 infra/deploy.py가 한다.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATA_MODE", "live")
sys.path.insert(0, str(ROOT / "backend"))
from app.pipeline.market import curated_rows  # noqa: E402

OUT = ROOT / "backend" / ".data" / "curated"


def main():
    posts, skills = curated_rows()
    for name, rows in (("postings", posts), ("posting_skills", skills)):
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "part-0000.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows):,}행 → {d.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
