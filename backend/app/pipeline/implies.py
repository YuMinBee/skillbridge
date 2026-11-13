"""상하위 스킬 보완. 'MySQL로 DB 설계'를 썼는데 'SQL' 필수가 갭으로 나오면 안 된다.

하위 스킬(구체 도구)을 가졌으면 상위 스킬(일반 역량)도 같은 근거로 인정한다.
- 명백한 포함 관계만 둔다 (MySQL ⊂ SQL, PyTorch ⊂ 딥러닝). 'FastAPI면 REST API' 같은 추정은 넣지 않는다.
- 상위 → 하위로는 내려가지 않는다 (SQL을 안다고 MySQL을 아는 건 아니다).
- 이미 상위 스킬 근거가 더 강하면 그대로 둔다.
- 추출 평가(eval)는 이 보완 전 결과로 잰다. 보완은 점수 계산 단계의 규칙이다.
"""
from .extract import RANK

PARENT: dict[str, str] = {
    **dict.fromkeys(["mysql", "postgresql", "oracle_db"], "sql"),
    **dict.fromkeys(["mongodb", "redis"], "nosql"),
    **dict.fromkeys(["pytorch", "tensorflow", "keras", "jax"], "deep_learning"),
    **dict.fromkeys(["deep_learning", "scikit_learn", "xgboost"], "machine_learning"),
    **dict.fromkeys(["opencv", "yolo"], "computer_vision"),
    **dict.fromkeys(["aws_eks", "helm"], "kubernetes"),
    **dict.fromkeys(["github_actions", "jenkins", "gitlab_ci", "argocd"], "cicd"),
    **dict.fromkeys(["aws_ec2", "aws_s3", "aws_lambda", "aws_ecs", "aws_rds", "aws_dynamodb", "aws_vpc",
                     "aws_iam", "aws_cloudformation", "aws_athena", "aws_glue", "aws_cloudwatch",
                     "aws_api_gateway", "aws_kinesis", "aws_redshift", "aws_sagemaker", "amazon_bedrock"], "aws"),
    **dict.fromkeys(["langchain", "llamaindex", "rag", "fine_tuning"], "llm"),
    "ugui": "unity",
}


def ancestors(sid: str) -> list[str]:
    out = []
    while sid in PARENT and PARENT[sid] not in out:
        sid = PARENT[sid]
        out.append(sid)
    return out


def expand(status_map: dict[str, dict]) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """→ (보완된 상태표, [(상위, 근거가 된 하위)]). 입력은 바꾸지 않는다."""
    out = dict(status_map)
    added = []
    for sid, v in sorted(status_map.items(), key=lambda x: -RANK[x[1]["status"]]):
        for anc in ancestors(sid):
            cur = out.get(anc)
            if cur is None or RANK[cur["status"]] < RANK[v["status"]]:
                out[anc] = {**v, "implied_by": sid}
                added.append((anc, sid))
    return out, added
