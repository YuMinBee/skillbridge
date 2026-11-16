"""블로그 원문 → 글쓴이 팀이 실제로 쓰는 기술 (공고는 보여주지 않는다). 결과를 캐시해 재실행 시 호출하지 않는다."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]  # 레포 루트
sys.path.insert(0, str(REPO / "backend"))
from app.adapters import bedrock
from app.pipeline.extract import _locate
from app.pipeline.normalize import normalize

SYS = """너는 기술 블로그 글에서, 글쓴이 팀이 실무에서 실제로 쓰거나 운영하거나 구현했다고 서술한 기술을 빠짐없이 추출한다.
- 기술만: 프로그래밍 언어, 프레임워크·라이브러리, 도구, 클라우드 서비스, 데이터베이스, 기술 분야.
- 제외: 사이드바·태그 목록·관련 글·다른 글 제목·광고·회사 소개 문구, 앞으로 도입할 계획, 검토만 하고 쓰지 않은 대안, 비교 대상으로만 언급한 기술, 일반명사로 쓰인 단어(예: 사회적 네트워크).
- mention: 글에 쓰인 표현 그대로. standard_name: 일반적인 표준 이름(보통 영문).
- evidence: 그 기술을 실제로 썼다는 문장을 그대로 복사한다."""
SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object",
    "properties": {"mention": {"type": "string"}, "standard_name": {"type": "string"}, "evidence": {"type": "string"}},
    "required": ["mention", "evidence"]}}}, "required": ["items"]}

def blog_skills(text, cache_file):
    cf = Path(cache_file)
    if cf.exists(): return json.loads(cf.read_text(encoding="utf-8"))
    log = bedrock.CallLog()
    out = bedrock.converse_tool(SYS, f"<글>\n{text}\n</글>", "submit_skills", SCHEMA, log=log, kind="extract", max_tokens=6000)
    ms = []
    for it in out.get("items", []):
        ev = _locate(it.get("evidence", ""), it.get("mention", ""), text)
        if ev is not None:
            ms.append({"mention": it["mention"].strip(), "standard_name": (it.get("standard_name") or "").strip(), "evidence": ev, "section": "duty"})
    normalize(ms, log=log)
    res = [{"skill_id": s, "mention": m["mention"], "evidence": m["evidence"][:160]} for m in ms for s in m["skill_ids"]]
    cf.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
