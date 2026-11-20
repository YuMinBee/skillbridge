"""시연 직전 캐시 채우기. 시연에서 올릴 바로 그 파일을 배포 주소로 한 번 분석해 둔다.

python scripts/prewarm.py            → docs/pivot/captures/demo_resume.docx를 만들고(없으면) 민간·자동으로 분석
같은 파일이면 24시간 동안 STAR·과제가 캐시에서 나와 시연이 빨라지고, 결과도 리허설 때와 같다.
시연 때는 반드시 docs/pivot/captures/demo_resume.docx를 올린다(글자가 하나라도 다르면 캐시가 안 맞음).
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import smoke_deploy as S  # noqa: E402

DOCX = ROOT / "docs" / "pivot" / "captures" / "demo_resume.docx"


def main():
    if not DOCX.exists():
        DOCX.write_bytes(S.docx_bytes(S.DEMO))
        print("만듦:", DOCX.relative_to(ROOT))
    t0 = time.time()
    r = S.run_case("시연 파일", files=[("demo_resume.docx", DOCX.read_bytes(),
                                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])
    print(("✓" if r["ok"] else "✗"), r["detail"], f"(총 {time.time() - t0:.0f}초)")
    print("한 번 더 돌리면 캐시에서 나와 더 빨라야 한다. 시연 전에 두 번 돌려 확인.")


if __name__ == "__main__":
    main()
