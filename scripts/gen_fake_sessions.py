"""기업 콘솔 익명 집계 시연용 가상 진단 기록 200건 (시드 고정).

개인 정보는 없고 '기업 + 막힌 스킬 목록 + 스킬별 상태 코드(보유/부분/검증 필요/없음)'만 담는다.
상태 코드는 기업 콘솔의 '기준 시뮬레이터'가 지원자 풀의 준비도를 다시 계산하는 데 쓴다.
실행: python scripts/gen_fake_sessions.py  → seed/sessions/fake_sessions.jsonl
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261110
# 기업별로 지원자가 막힐 확률 (가상)
BLOCK_P = {
    "A": {"edge_ai": .71, "cpp": .54, "ros": .50, "computer_vision": .33, "docker": .29, "pytorch": .18, "python": .05},
    "B": {"observability": .62, "terraform": .58, "kubernetes": .44, "linux": .21, "aws": .17, "docker": .15, "python": .12},
    "C": {"amazon_bedrock": .66, "mlops": .52, "rag": .38, "llm": .31, "aws": .30, "docker": .22, "sql": .14, "python": .04},
}


def main():
    rnd = random.Random(SEED)
    out = ROOT / "seed" / "sessions" / "fake_sessions.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for i in range(200):
            c = rnd.choices(["A", "B", "C"], [0.4, 0.35, 0.25])[0]
            profile = {}
            for s, p in BLOCK_P[c].items():
                if rnd.random() < p:  # 막힘 → 없음/부분/검증 필요
                    profile[s] = rnd.choices(["miss", "part", "verify"], [0.5, 0.3, 0.2])[0]
                else:
                    profile[s] = "own"
            gaps = [s for s, st in profile.items() if st != "own"]
            profile = {s: st for s, st in profile.items() if st != "miss"}  # 없음은 기록하지 않음 (실제 진단과 같은 형식)
            f.write(json.dumps({"id": f"F{i:03d}", "company": c, "gaps": gaps, "profile": profile, "fake": True},
                               ensure_ascii=False) + "\n")
    print(f"200 sessions -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
