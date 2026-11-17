"""청크 나누기. 전략 이름 하나로 실험 조합을 고른다.

- fixed{N}o{P}  : 고정 토큰 N개, 겹침 P% (예: fixed300o15, fixed500o0)
- hier{P}_{C}   : 계층형. 자식 C토큰으로 검색하고, 결과에는 부모 P토큰 본문을 돌려준다 (예: hier1500_300)
- struct        : 구조 단위. 줄 하나 = 청크 하나 (NCS 수행준거 한 줄)

토큰 수 계산 (모델 토크나이저 없이 근사): 한글 음절 1개 = 1, 영문 단어·숫자 묶음 1개 = 1, 그 밖의 기호 1개 = 1.
Titan은 응답에 실제 토큰 수(inputTextTokenCount)를 주므로 embed_cache가 그 값을 같이 저장한다.
# ponytail: 근사 토큰. 실제 토큰 수와 비율이 크게 다르면 그 비율로 N을 보정한다.
"""
import re

_TOK = re.compile(r"[가-힣]|[A-Za-z]+|\d+|[^\sA-Za-z\d가-힣]")
STRATEGIES = [f"fixed{n}o{p}" for n in (200, 300, 500, 1000) for p in (0, 15)] + ["hier1500_300", "struct"]


def ntokens(text: str) -> int:
    return len(_TOK.findall(text))


def _windows(text: str, size: int, overlap: int) -> list[str]:
    spans = [m.span() for m in _TOK.finditer(text)]
    if not spans:
        return []
    step = max(1, size - overlap)
    out = []
    for i in range(0, len(spans), step):
        part = spans[i:i + size]
        out.append(text[part[0][0]:part[-1][1]])
        if i + size >= len(spans):
            break
    return out


def split(text: str, strategy: str) -> list[dict]:
    """→ [{text, parent}] (parent는 계층형에서만 자식과 다르다)"""
    if strategy == "struct":
        return [{"text": ln.strip(), "parent": ln.strip()} for ln in text.splitlines() if ln.strip()]
    if m := re.fullmatch(r"fixed(\d+)o(\d+)", strategy):
        n, p = int(m[1]), int(m[2])
        return [{"text": t, "parent": t} for t in _windows(text, n, n * p // 100)]
    if m := re.fullmatch(r"hier(\d+)_(\d+)", strategy):
        return [{"text": c, "parent": par}
                for par in _windows(text, int(m[1]), 0) for c in _windows(par, int(m[2]), 0)]
    raise ValueError(f"모르는 청크 전략: {strategy}")


def chunk_docs(docs: list[dict], strategy: str) -> list[dict]:
    """코퍼스 문서(CONTRACTS 1절) → 청크. 검색 결과 모양에 필요한 필드를 문서에서 물려받는다."""
    out = []
    for d in docs:
        for i, c in enumerate(split(d["text"], strategy)):
            out.append({"chunk_id": f"{d['doc_id']}#{strategy}#{i}", "doc_id": d["doc_id"], "kind": d["kind"],
                        "title": d.get("title", ""), "url": d.get("url"), "meta": d.get("meta", {}), **c})
    return out
