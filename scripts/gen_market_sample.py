"""시장 탭용 가상 공고 샘플 생성 (DATA_MODE=sample).

실제 공고가 아니다. 월별 추세(급상승/하락)가 보이도록 확률을 조정한 합성 데이터이며,
본문에는 스킬 별칭을 섞어 써서 정규화 파이프라인이 실제로 동작하게 한다.
실행: python scripts/gen_market_sample.py  → seed/market/postings_sample.jsonl
"""
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261109
MONTHS = [f"{y}-{m:02d}" for y, m in [(2025, 11), (2025, 12)] + [(2026, i) for i in range(1, 11)]]

UP2, UP, FLAT, DOWN = 1.2, 0.5, 0.0, -0.5
POOLS = {
    "ai": {
        "python": (.85, FLAT), "pytorch": (.5, UP), "tensorflow": (.35, DOWN), "deep_learning": (.45, FLAT),
        "machine_learning": (.4, FLAT), "computer_vision": (.28, FLAT), "nlp": (.22, FLAT), "llm": (.32, UP2),
        "rag": (.18, UP2), "amazon_bedrock": (.07, UP2), "langchain": (.12, UP), "vector_db": (.11, UP),
        "prompt_engineering": (.11, UP), "ai_agent": (.05, UP2), "mlops": (.2, UP), "mlflow": (.09, FLAT),
        "docker": (.32, FLAT), "kubernetes": (.18, FLAT), "aws": (.32, FLAT), "aws_sagemaker": (.11, FLAT),
        "sql": (.28, FLAT), "fastapi": (.14, UP), "git": (.22, FLAT), "linux": (.22, FLAT),
        "huggingface": (.14, UP), "fine_tuning": (.11, UP), "paper_research": (.18, FLAT), "cuda": (.09, FLAT),
        "hadoop": (.06, DOWN), "spark": (.11, FLAT), "pandas": (.18, FLAT),
        "edge_ai": (.08, UP), "cpp": (.15, FLAT), "ros": (.05, FLAT),
    },
    "cloud": {
        "aws": (.8, FLAT), "linux": (.6, FLAT), "kubernetes": (.42, UP), "docker": (.48, FLAT),
        "terraform": (.28, UP), "cicd": (.33, FLAT), "networking": (.33, FLAT), "python": (.38, FLAT),
        "shell": (.28, FLAT), "aws_eks": (.14, UP), "prometheus": (.14, FLAT), "grafana": (.11, FLAT),
        "ansible": (.1, FLAT), "azure": (.2, FLAT), "gcp": (.14, FLAT), "ncp": (.12, FLAT),
        "aws_cert": (.24, FLAT), "security": (.2, FLAT), "java": (.15, DOWN), "virtualization": (.15, DOWN),
        "finops": (.05, UP), "serverless": (.1, FLAT), "aws_lambda": (.12, FLAT), "cloud_migration": (.15, FLAT),
        "amazon_bedrock": (.03, UP2), "argocd": (.07, UP), "github_actions": (.12, UP), "jenkins": (.15, DOWN),
        "observability": (.2, UP),
    },
}
REGION_BOOST = {"대경권": {"computer_vision": .15, "edge_ai": .1, "smart_factory": .2, "anomaly_detection": .12}}
CORE = {"python", "aws", "linux"}
DUTY = {
    "ai": ["AI 모델 개발 및 고도화", "데이터 기반 예측 모델 연구", "생성형 AI 서비스 기획 및 개발", "모델 학습·평가 파이프라인 운영"],
    "cloud": ["고객사 인프라 구축 및 운영", "서비스 운영과 장애 대응", "고객사 시스템 이전 지원", "운영 환경 안정성 개선"],
}
# 담당업무 문구는 스킬 별칭과 겹치지 않게 쓴다 (겹치면 언급률이 부풀려짐)
REQ_T = ["{a} 활용 경험", "{a} 실무 경험 {n}년 이상", "{a} 기반 개발 경험", "{a}에 대한 이해와 사용 경험"]
PREF_T = ["{a} 경험자 우대", "{a} 프로젝트 경험", "{a} 활용 가능자"]


def load_aliases():
    out = {}
    with open(ROOT / "data" / "skills.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            names = [r["canonical"]] + [x for x in (r["aliases_ko"] + "|" + r["aliases_en"]).split("|") if x]
            out[r["skill_id"]] = names
    return out


def main():
    rnd = random.Random(SEED)
    aliases = load_aliases()
    rows, n = [], 0
    for mi, month in enumerate(MONTHS):
        x = (mi - (len(MONTHS) - 1) / 2) / len(MONTHS)  # -0.46 ~ +0.46
        for _ in range(60):
            n += 1
            job = "ai" if rnd.random() < 0.55 else "cloud"
            region = rnd.choices(["대경권", "수도권", "기타"], [0.3, 0.5, 0.2])[0]
            pool = dict(POOLS[job])
            for sid, b in REGION_BOOST.get(region, {}).items():
                if job == "ai":
                    base, tr = pool.get(sid, (0, FLAT))
                    pool[sid] = (base + b, tr)
            req, pref = [], []
            for sid, (base, trend) in pool.items():
                p = min(0.95, max(0.0, base * (1 + trend * x * 2)))
                if rnd.random() < p:
                    a = rnd.choice(aliases[sid][:3])
                    (req if sid in CORE or rnd.random() < 0.6 else pref).append(a)
            if not req:
                req.append(aliases["python" if job == "ai" else "aws"][0])
            lines = ["담당업무"] + [f"- {d}" for d in rnd.sample(DUTY[job], 2)]
            lines += ["자격요건"] + [f"- {rnd.choice(REQ_T).format(a=a, n=rnd.randint(1, 3))}" for a in req]
            if pref:
                lines += ["우대사항"] + [f"- {rnd.choice(PREF_T).format(a=a)}" for a in pref]
            rows.append({
                "id": f"S{n:04d}",
                "source": "가상 샘플 (scripts/gen_market_sample.py)",
                "company": f"샘플기업{rnd.randint(1, 120):03d}(가상)",
                "title": "AI 엔지니어" if job == "ai" else "클라우드 엔지니어",
                "job": job,
                "region": region,
                "date": f"{month}-{rnd.randint(1, 28):02d}",
                "text": "\n".join(lines),
            })
    out = ROOT / "seed" / "market" / "postings_sample.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} postings -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
