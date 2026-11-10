"""기업 지식베이스 검색 (M4). Bedrock Knowledge Base (S3 Vectors · Titan Text Embeddings V2).

멀티테넌시 원칙 (명세 4장): KB 하나를 공유하고 문서마다 tenantId 메타데이터를 붙인다.
**필터는 이 함수 안에서 강제로 넣는다.** 호출자는 tenant_id만 넘기고, 필터를 바꾸거나 끌 방법이 없다.
tenant_id는 라우터가 저장소에 있는 기업인지 확인한 값이다 (클라이언트가 보낸 값을 그대로 믿지 않는다).

KB_ID가 없거나 MOCK 모드면 seed/corp-docs/{tenant}/ 안에서만 키워드로 찾는다 (같은 tenant 격리).
"""
import re
from pathlib import Path

from ..config import BEDROCK_MOCK, KB_ID, SEED, boto_session

_TID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class TenantError(ValueError):
    pass


def mode() -> str:
    return "kb" if (KB_ID and not BEDROCK_MOCK) else "local"


def tenant_filter(tenant_id: str) -> dict:
    if not _TID.match(tenant_id or ""):
        raise TenantError("잘못된 tenant_id")
    return {"equals": {"key": "tenantId", "value": tenant_id}}


def _client():
    from botocore.config import Config
    return boto_session().client("bedrock-agent-runtime", config=Config(read_timeout=30, retries={"max_attempts": 3}))


def retrieve(tenant_id: str, query: str, k: int = 3, client=None) -> list[dict]:
    """→ [{text, source, score, tenant}] — 항상 해당 tenant 문서만."""
    flt = tenant_filter(tenant_id)
    if mode() == "local" and client is None:
        return _local(tenant_id, query, k)
    cl = client or _client()
    res = cl.retrieve(knowledgeBaseId=KB_ID, retrievalQuery={"text": query[:1000]},
                      retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": k, "filter": flt}})
    out = []
    for r in res.get("retrievalResults", []):
        meta = r.get("metadata", {}) or {}
        # 이중 방어: 필터가 있어도 응답의 tenant가 다르면 버린다
        if meta.get("tenantId") not in (None, tenant_id):
            continue
        uri = (r.get("location", {}).get("s3Location", {}) or {}).get("uri", "")
        out.append({"text": r["content"]["text"].strip(), "source": uri.rsplit("/", 1)[-1], "score": round(r.get("score", 0), 3),
                    "tenant": meta.get("tenantId", tenant_id)})
    return out


def _local(tenant_id: str, query: str, k: int) -> list[dict]:
    d = Path(SEED) / "corp-docs" / tenant_id
    if not d.is_dir():
        return []
    terms = [t for t in re.split(r"\s+", query.strip()) if t]
    hits = []
    for f in sorted(d.glob("*.md")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sc = sum(line.lower().count(t.lower()) for t in terms)
            if sc:
                hits.append({"text": line, "source": f.name, "score": float(sc), "tenant": tenant_id})
    hits.sort(key=lambda h: -h["score"])
    return hits[:k]
