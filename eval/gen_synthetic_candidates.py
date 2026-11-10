"""갭을 일부러 심은 합성 지원자 30명 (기업 A·B·C × 10명, seed 고정).

- 기업 요구역량마다 상태를 정해 둔다: 보유(own) / 부분(part) / 검증 필요(verify) / 없음(miss).
- 이력서 문장은 상태별 템플릿으로 만들고, 기술명은 한국어 표기 변형 중 하나를 쓴다.
  변형 목록은 사전(data/skills.csv)과 독립적으로 사람이 적은 것이다. 사전에 있는지는 생성 시
  실제 SkillDict로 확인해 in_dict로 기록한다 (사전 밖 표기 → 규칙 엔진이 놓치는 경우를 재기 위해).
- 정답: gold_status {skill_id: 상태}. 갭 = 보유가 아닌 요구역량.
- 요구역량이 아닌 기술(방해 요소)도 1~2개 넣는다.
출력: eval/synthetic_candidates.jsonl
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.skills import get_dict  # noqa: E402

VARIANTS = {
    "python": ["Python", "파이썬", "파이선"],
    "pytorch": ["PyTorch", "파이토치", "토치"],
    "computer_vision": ["컴퓨터 비전", "객체 탐지", "비전 AI"],
    "edge_ai": ["엣지 AI", "온디바이스 AI", "엣지 디바이스 추론"],
    "docker": ["Docker", "도커", "컨테이너 이미지"],
    "cpp": ["C++", "씨쁠쁠", "CPP"],
    "ros": ["ROS", "ROS2", "로봇 운영체제"],
    "aws": ["AWS", "아마존 웹 서비스", "아마존 클라우드"],
    "linux": ["Linux", "리눅스", "우분투 서버"],
    "terraform": ["Terraform", "테라폼", "TF 모듈"],
    "observability": ["모니터링", "관측성", "옵저버빌리티"],
    "kubernetes": ["Kubernetes", "쿠버네티스", "k8s"],
    "llm": ["LLM", "대규모 언어 모델", "GPT 계열 모델"],
    "rag": ["RAG", "검색 증강 생성", "리트리버 기반 QA"],
    "amazon_bedrock": ["Amazon Bedrock", "베드록", "AWS 베드락"],
    "sql": ["SQL", "에스큐엘", "쿼리 작성"],
    "mlops": ["MLOps", "모델 서빙", "엠엘옵스"],
}
DISTRACT = ["React", "Java", "Figma", "Spring", "Unity"]
OWN_T = ["졸업작품에서 {v}로 {thing} 직접 개발했습니다.", "인턴 기간 동안 {v} 기반 {thing} 구축하고 운영했습니다.",
         "팀 프로젝트에서 {v}를 사용해 {thing} 구현했습니다."]
PART_T = ["부트캠프 수업에서 {v}를 실습했습니다.", "{v} 온라인 강의를 수강했습니다.", "스터디에서 {v} 기초를 공부했습니다."]
THINGS = ["불량 검출 서비스", "사내 검색 도구", "배포 자동화 스크립트", "데이터 수집기", "모니터링 대시보드"]
STATUS_P = [("own", .45), ("part", .2), ("verify", .15), ("miss", .2)]
SEED = 6


def _obj(w: str) -> str:
    """목적격 조사: 받침 있으면 을, 없으면 를"""
    c = ord(w[-1]) - 0xAC00
    return w + ("을" if 0 <= c < 11172 and c % 28 else "를")


def main():
    sd = get_dict()
    rng = random.Random(SEED)
    comps = {t: json.loads((ROOT / f"seed/companies/{t}.json").read_text(encoding="utf-8")) for t in "ABC"}
    out = []
    for t, comp in comps.items():
        reqs = list(comp["requirements"])
        for k in range(10):
            gold, lines, listed, used = {}, ["[학력] OO대학교 4학년"], [], {}
            for sid in reqs:
                st = rng.choices([s for s, _ in STATUS_P], [p for _, p in STATUS_P])[0]
                gold[sid] = st
                if st == "miss":
                    continue
                v = rng.choice(VARIANTS[sid])
                used[sid] = {"variant": v, "in_dict": sid in {m["skill_id"] for m in sd.find(v)}}
                if st == "own":
                    lines.append("- " + rng.choice(OWN_T).format(v=v, thing=_obj(rng.choice(THINGS))))
                elif st == "part":
                    lines.append("- " + rng.choice(PART_T).format(v=v))
                else:
                    listed.append(v)
            listed += rng.sample(DISTRACT, rng.randint(1, 2))
            rng.shuffle(listed)
            lines.append("[보유기술] " + ", ".join(listed))
            out.append({"id": f"syn-{t}{k + 1:02d}", "company": t, "resume": "\n".join(lines),
                        "gold_status": gold, "variants": used})
    path = ROOT / "eval/synthetic_candidates.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = sum(len(r["variants"]) for r in out)
    oov = sum(not v["in_dict"] for r in out for v in r["variants"].values())
    print(f"{len(out)}명 → {path.relative_to(ROOT)} · 언급 {n}개 중 사전 밖 표기 {oov}개")


if __name__ == "__main__":
    main()
