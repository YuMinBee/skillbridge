"""웹 방식 기준선: 같은 Bedrock Claude 모델에 사람이 웹 채팅에 치듯 프롬프트 한 번.

비교의 핵심은 "모델은 같고 시스템만 다르다"이다. 그래서 여기서는
- 우리 시스템과 같은 모델(MODEL_ID)을 쓴다.
- 시스템 프롬프트·검색·규칙·검증·도구가 없다. 사용자 메시지 하나뿐이다.
- temperature는 기본 1.0(API 기본값, 웹 채팅처럼 매번 조금씩 다른 답). 0도 돌려서 둘 다 비교한다.

프롬프트 두 가지 (--prompt)
- plain: 사람이 웹 채팅에 그냥 치는 말. "STAR로 분석해 주세요", "역량 분석하고 과제 추천해 줘"
- good : 잘 쓴 프롬프트. "STAR로 나누고 각 칸은 원문 문장 그대로 인용, 없으면 비움, 과정은 실제 있는 것만"
  → "프롬프트만 잘 쓰면 웹으로도 되잖아"에 답하려면 good도 이겨야 한다(또는 진 만큼 그대로 보고한다).
  good도 검색·카탈로그·검증은 없다. 사용자가 웹 채팅에서 할 수 있는 것은 프롬프트뿐이기 때문이다.

과제
- star: gold_star_{split}.jsonl의 경험 단락 → "STAR 기준으로 분석해 주세요"
- reco: gold_reco_{split}.jsonl의 이력서 → "내 역량 분석하고 과제·교육과정 추천해 줘"

답변(자유 글)은 원문 그대로 저장하고, 평가를 위해 FAST 모델(temperature 0)로 JSON에 옮긴다.
파서는 **답변만** 본다(이력서·정답을 보지 않는다). 그래서 파서가 판정을 바꿀 수 없다.
원문이 남아 있으므로 파서를 고치면 --reparse로 다시 옮길 수 있다.

사용 (aws sso login --profile kosa 뒤)
  python eval/trust/baseline_web.py --task star --split dev --runs 5 --dry-run   # 호출 수·대략 비용만
  python eval/trust/baseline_web.py --task star --split dev --runs 5                       # plain, t=1
  python eval/trust/baseline_web.py --task star --split dev --runs 5 --temperature 0
  python eval/trust/baseline_web.py --task star --split dev --runs 5 --prompt good
  python eval/trust/baseline_web.py --task star --split dev --runs 5 --prompt good --temperature 0
  python eval/trust/baseline_web.py --task reco --split dev --runs 5
  python eval/trust/baseline_web.py --task star --split test --runs 5 --final    # test는 마지막 한 번
  python eval/trust/baseline_web.py --task star --split dev --mock --limit 3      # AWS 없이 형식 확인

출력: eval/trust/predictions/web_{task}_{split}_{prompt}_t{temperature}.jsonl, 한 줄 = (id, run).
  예) web_star_dev_plain_t1.jsonl, web_star_dev_good_t0.jsonl
이미 저장된 (id, run)은 건너뛴다. 중간에 끊겨도 같은 명령으로 이어서 돌리면 된다.
"""
import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))

OUT_DIR = HERE / "predictions"

JOB_LABEL = {"backend": "백엔드 개발자", "ai_ml": "AI·머신러닝 엔지니어", "data": "데이터 분석가"}

# 사람이 웹 Claude 채팅창에 칠 법한 문장. 시스템 프롬프트 없음.
# plain = 그냥 묻기, good = 잘 쓴 프롬프트(인용·비움·지어내지 않기를 직접 요구). 둘 다 사용자 메시지 하나.
STAR_PROMPT = ("아래는 제 이력서에 쓴 경험이에요. STAR(상황·과제·행동·결과) 기준으로 분석해 주세요. "
               "각 항목이 드러나는지, 이 경험이 강점으로 얼마나 설득력 있는지도 알려 주세요.\n\n{text}")
RECO_PROMPT = ("제 이력서예요. {job} 직무로 취업하려고 해요. 내 역량 분석하고, 부족한 부분을 채울 과제랑 "
               "들을 만한 교육과정 추천해 줘.\n\n{resume}")

STAR_PROMPT_GOOD = (
    "아래는 제 이력서에 쓴 경험이에요. STAR(상황·과제·행동·결과)로 나눠 주세요.\n"
    "규칙:\n"
    "1. 각 칸(S·T·A·R)에는 아래 원문에 있는 문장을 고치지 말고 그대로 인용하세요. 요약하거나 바꿔 쓰지 마세요.\n"
    "2. 원문에 그 칸에 해당하는 내용이 없으면 칸을 비우고 '없음'이라고만 쓰세요. 예시를 지어내지 마세요.\n"
    "3. 결과(R)에 원문에 적힌 수치 성과가 있는지, 글쓴이 본인이 한 역할이 분명한지 각각 예/아니오로 답하세요.\n"
    "4. 마지막에 이 경험이 강점으로 얼마나 설득력 있는지 한 줄로 평가하세요.\n\n"
    "원문:\n{text}")
RECO_PROMPT_GOOD = (
    "제 이력서예요. {job} 직무로 취업하려고 해요.\n"
    "규칙:\n"
    "1. 강점과 부족한 역량을 나눠서 쓰고, 각각 이력서 원문 문장을 그대로 인용해 근거로 붙이세요. "
    "원문에 없는 경험은 지어내지 마세요.\n"
    "2. 부족한 역량을 채울 과제를 우선순위대로 추천하세요.\n"
    "3. 교육과정은 실제로 있는 과정만, 정확한 과정명과 운영 기관을 써서 추천하세요. "
    "실제로 있는지 확실하지 않으면 추천하지 마세요.\n\n"
    "이력서:\n{resume}")


def _star_criteria() -> str:
    """우리 시스템 지시문(star._SYS)의 '칸 기준' 문단을 그대로 가져온다. 우리와 같은 기준을 웹에도 준다(웹 ③)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    from app.agents import star  # noqa: E402
    lines, on = [], False
    for l in star._SYS.splitlines():
        if l.startswith("- 칸 기준"):
            on = True
        elif on and l.startswith("- "):
            break
        if on:
            lines.append(l.lstrip("- ").rstrip())
    return "\n".join(lines)


# strict = 웹 ③: good + 우리 시스템과 똑같은 칸 기준. "너희만 기준을 줬잖아"에 답하기 위한 것.
# 이것과도 차이가 나면 차이는 프롬프트가 아니라 시스템(원문 대조·규칙 점수·검증)에서 나온 것이다.
STAR_PROMPT_STRICT = STAR_PROMPT_GOOD.replace("\n\n원문:\n{text}", "\n5. " + _star_criteria().replace("{", "{{").replace("}", "}}") + "\n\n원문:\n{text}")

PROMPTS = {"plain": {"star": STAR_PROMPT, "reco": RECO_PROMPT},
           "good": {"star": STAR_PROMPT_GOOD, "reco": RECO_PROMPT_GOOD},
           "strict": {"star": STAR_PROMPT_STRICT, "reco": RECO_PROMPT_GOOD}}

# ── 파서: 답변 글 → JSON (답변에 적힌 판단만 옮긴다) ──────────────────────────
PARSE_SYSTEM = (
    "너는 다른 AI가 쓴 답변을 JSON으로 옮기는 변환기다. 답변에 적힌 판단만 옮기고, 네 판단은 더하지 않는다. "
    "원래 이력서는 너에게 주어지지 않는다. 답변에 없는 내용은 비워 둔다."
)

STAR_PARSE_RULES = """규칙
- status: 답변이 그 항목이 경험에 드러난다고 했으면 "present", 있긴 하지만 부족·모호하다고 했으면 "weak",
  없다·드러나지 않는다·빠졌다고 했거나 칸을 비우고 "없음"이라 적었으면 "absent", 답변이 그 항목을 언급하지 않았으면 "unmentioned".
- 답변이 예시를 지어 "이렇게 쓰면 좋다"고 제안만 한 내용은 그 항목이 있다는 근거가 아니다.
- claim: 답변이 그 항목의 내용으로 제시한 문장을 답변에 쓰인 그대로 옮긴다(150자 이내). 없으면 null.
- quantified: 답변이 결과에 수치·정량 성과가 있다고 했으면 true, 없다고 했으면 false, 언급 없으면 null.
- my_role_clear: 답변이 글쓴이 본인의 역할이 분명하다고 했으면 true, 불분명하다고 했으면 false, 언급 없으면 null.
- overall: 답변의 전체 평가가 강점으로 설득력이 높다는 쪽이면 "strong", 보통·보완하면 좋다는 쪽이면 "ok",
  약하다·설득력이 부족하다는 쪽이면 "weak", 전체 평가가 없으면 "unclear"."""

_SLOT = {"type": "object", "properties": {
    "status": {"type": "string", "enum": ["present", "weak", "absent", "unmentioned"]},
    "claim": {"type": ["string", "null"]}}, "required": ["status", "claim"]}
STAR_SCHEMA = {"type": "object", "properties": {
    "S": _SLOT, "T": _SLOT, "A": _SLOT, "R": _SLOT,
    "quantified": {"type": ["boolean", "null"]},
    "my_role_clear": {"type": ["boolean", "null"]},
    "overall": {"type": "string", "enum": ["strong", "ok", "weak", "unclear"]}},
    "required": ["S", "T", "A", "R", "quantified", "my_role_clear", "overall"]}

RECO_PARSE_RULES = """규칙
- strengths: 답변이 강점이라고 한 것(짧은 구, 답변 표현 그대로). gaps: 부족하다고 한 것.
- tasks: 답변이 하라고 추천한 과제·프로젝트를 답변 순서대로. title은 답변 표현 그대로(100자 이내).
- courses: 답변이 추천한 교육과정·강의·자격증·책을 하나씩. name은 답변에 쓰인 이름 그대로.
  "온라인 강의", "AWS 공부하기"처럼 특정할 수 없는 일반 명사만 있으면 specific=false.
  kind: 교육과정·강의 "course", 자격증 "certification", 책 "book", 그 밖 "other".
  provider·url은 답변에 있을 때만."""

RECO_SCHEMA = {"type": "object", "properties": {
    "strengths": {"type": "array", "items": {"type": "string"}},
    "gaps": {"type": "array", "items": {"type": "string"}},
    "tasks": {"type": "array", "items": {"type": "object", "properties": {
        "rank": {"type": "integer"}, "title": {"type": "string"}}, "required": ["rank", "title"]}},
    "courses": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"},
        "kind": {"type": "string", "enum": ["course", "certification", "book", "other"]},
        "specific": {"type": "boolean"},
        "provider": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]}}, "required": ["name", "kind", "specific"]}}},
    "required": ["strengths", "gaps", "tasks", "courses"]}

# 대략 비용 추정용(--dry-run). 실제 청구는 Bedrock 가격표·Cost Explorer로 확인한다. 토큰 수는 결과에 실제 값을 남긴다.
EST_USD_PER_MTOK = {"main": (3.0, 15.0), "parse": (1.0, 5.0)}
EST_TOKENS = {"star": {"main": (250, 900), "parse": (1400, 350)},
              "reco": {"main": (700, 1800), "parse": (2500, 600)}}


def load_inputs(task: str, split: str) -> list[dict]:
    name = f"gold_{task}_{split}.jsonl"
    path = HERE / name
    if not path.exists():
        sys.exit(f"{name}이 없습니다. (reco 정답셋은 구현 목록 6번)")
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if task == "star":
        rows = [r for r in rows if r.get("labeler", "A") == "A"]
    return rows


def make_prompt(task: str, row: dict, style: str = "plain") -> str:
    tpl = PROMPTS[style][task]
    if task == "star":
        return tpl.format(text=row["text"])
    return tpl.format(job=JOB_LABEL.get(row["job_family"], row["job_family"]), resume=row["resume"])


def done_keys(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    keys = set()
    for l in path.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            if r.get("answer") is not None:
                keys.add((r["id"], r["run"]))
    return keys


# ── Bedrock 호출 ───────────────────────────────────────────────────────────
def ask_web(prompt: str, model: str, temperature: float, max_tokens: int) -> tuple[str, dict, int]:
    """시스템 프롬프트 없이 사용자 메시지 하나."""
    from app.adapters.bedrock import _wrap, client
    t0 = time.perf_counter()
    try:
        r = client().converse(modelId=model,
                              messages=[{"role": "user", "content": [{"text": prompt}]}],
                              inferenceConfig={"maxTokens": max_tokens, "temperature": temperature})
    except Exception as e:  # noqa: BLE001
        raise _wrap(e) from e
    ms = round((time.perf_counter() - t0) * 1000)
    text = "".join(c.get("text", "") for c in r["output"]["message"]["content"])
    u = r.get("usage", {})
    return text, {"in": u.get("inputTokens", 0), "out": u.get("outputTokens", 0),
                  "stop": r.get("stopReason")}, ms


def parse_answer(task: str, answer: str, model: str) -> tuple[dict, dict]:
    from app.adapters.bedrock import CallLog, converse_tool
    rules, schema = (STAR_PARSE_RULES, STAR_SCHEMA) if task == "star" else (RECO_PARSE_RULES, RECO_SCHEMA)
    log = CallLog()
    user = f"{rules}\n\n<답변>\n{answer}\n</답변>"
    parsed = converse_tool(PARSE_SYSTEM, user, "submit", schema, model=model, log=log, max_tokens=2000, kind="parse")
    c = log.calls[-1] if log.calls else {}
    return parsed, {"in": c.get("in", 0), "out": c.get("out", 0)}


# ── AWS 없이 형식 확인용 ─────────────────────────────────────────────────────
def mock_answer(task: str, row: dict, run: int) -> tuple[str, dict]:
    if task == "star":
        ans = f"[mock run {run}] 상황·과제·행동·결과가 모두 잘 드러나는 훌륭한 경험입니다."
        slot = {"status": "present", "claim": None}
        return ans, {"S": slot, "T": slot, "A": slot, "R": slot, "quantified": None,
                     "my_role_clear": None, "overall": "strong"}
    ans = f"[mock run {run}] 강점: 문제 해결. 추천 과제: 개인 프로젝트 배포. 추천 과정: 가상 부트캠프 A."
    return ans, {"strengths": ["문제 해결"], "gaps": ["배포 경험"],
                 "tasks": [{"rank": 1, "title": "개인 프로젝트 배포"}],
                 "courses": [{"name": "가상 부트캠프 A", "kind": "course", "specific": True,
                              "provider": None, "url": None}]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", choices=["star", "reco"], required=True)
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--runs", type=int, default=5, help="같은 입력 반복 횟수(일관성 측정용)")
    ap.add_argument("--prompt", choices=["plain", "good", "strict"], default="plain",
                    help="plain = 그냥 묻기, good = 잘 쓴 프롬프트(원문 인용·없으면 비움·실제 과정만)")
    ap.add_argument("--temperature", type=float, default=1.0, help="기본 1.0 = API 기본값(웹 채팅처럼). 0도 돌린다")
    ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--model", default=None, help="기본 MODEL_ID(.env) = 우리 시스템과 같은 모델")
    ap.add_argument("--parse-model", default=None, help="기본 FAST_MODEL_ID(.env)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N개 입력만")
    ap.add_argument("--dry-run", action="store_true", help="호출하지 않고 호출 수·대략 비용만 출력")
    ap.add_argument("--mock", action="store_true", help="AWS 없이 가짜 답으로 형식만 확인 (파일 이름에 _mock)")
    ap.add_argument("--reparse", action="store_true", help="저장된 답변을 다시 파싱만 한다")
    ap.add_argument("--final", action="store_true", help="test split 실행 확인 (마지막 한 번)")
    a = ap.parse_args()

    if a.split == "test" and not (a.final or a.dry_run):
        sys.exit("test는 마지막에 한 번만 돌린다(규칙 9). 정말이면 --final을 붙인다.")

    from app.config import FAST_MODEL_ID, MODEL_ID
    model = a.model or MODEL_ID
    parse_model = a.parse_model or FAST_MODEL_ID or MODEL_ID
    if not a.mock and not a.dry_run and not model:
        sys.exit(".env에 MODEL_ID가 없습니다.")

    rows = load_inputs(a.task, a.split)
    if a.limit:
        rows = rows[:a.limit]
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"web_{a.task}_{a.split}_{a.prompt}_t{a.temperature:g}{'_mock' if a.mock else ''}.jsonl"

    if a.reparse:
        return reparse(out, a.task, parse_model)

    have = done_keys(out)
    todo = [(r, k) for r in rows for k in range(1, a.runs + 1) if (r["id"], k) not in have]
    print(f"입력 {len(rows)}개 × {a.runs}회 = {len(rows) * a.runs}, 이미 있음 {len(have)}, 이번에 {len(todo)}회 호출")
    print(f"모델 {model or '(MODEL_ID 없음)'} · 프롬프트 {a.prompt} · temperature {a.temperature} · 파서 {parse_model} → {out.relative_to(ROOT)}")

    if a.dry_run:
        usd = 0.0
        for part in ("main", "parse"):
            tin, tout = EST_TOKENS[a.task][part]
            pin, pout = EST_USD_PER_MTOK[part]
            usd += len(todo) * (tin * pin + tout * pout) / 1e6
        print(f"대략 비용(추정, 가격표 확인 필요): ${usd:.2f}")
        return

    lock = threading.Lock()

    def one(row: dict, run: int) -> dict:
        prompt = make_prompt(a.task, row, a.prompt)
        rec = {"id": row["id"], "run": run, "task": a.task, "split": a.split, "prompt_style": a.prompt,
               "model": "mock" if a.mock else model, "temperature": a.temperature,
               "prompt": prompt, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if a.task == "reco":
            rec["job_family"] = row.get("job_family")
        if a.mock:
            rec["answer"], rec["parsed"] = mock_answer(a.task, row, run)
            rec["usage"], rec["ms"], rec["parse_model"] = {}, 0, "mock"
            return rec
        try:
            rec["answer"], rec["usage"], rec["ms"] = ask_web(prompt, model, a.temperature, a.max_tokens)
        except Exception as e:  # noqa: BLE001
            rec["answer"], rec["error"] = None, str(e)[:300]
            return rec
        rec["parse_model"] = parse_model
        try:
            rec["parsed"], rec["parse_usage"] = parse_answer(a.task, rec["answer"], parse_model)
        except Exception as e:  # noqa: BLE001  답변은 남기고 파싱만 실패로 기록 → --reparse
            rec["parsed"], rec["parse_error"] = None, str(e)[:300]
        return rec

    n_ok = n_err = 0
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex, out.open("a", encoding="utf-8") as f:
        futs = [ex.submit(one, r, k) for r, k in todo]
        for i, fu in enumerate(as_completed(futs), 1):
            rec = fu.result()
            with lock:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            if rec.get("answer") is None:
                n_err += 1
                print(f"  [{i}/{len(todo)}] {rec['id']}#{rec['run']} 실패: {rec.get('error')}")
                if "로그인 만료" in (rec.get("error") or ""):
                    ex.shutdown(cancel_futures=True)
                    break
            else:
                n_ok += 1
                if i % 10 == 0 or i == len(todo):
                    print(f"  [{i}/{len(todo)}] 진행 중")
    print(f"완료 {n_ok}, 실패 {n_err}. 실패한 것은 같은 명령으로 다시 돌리면 이어서 한다.")


def reparse(out: Path, task: str, parse_model: str):
    if not out.exists():
        sys.exit(f"{out.name}이 없습니다.")
    recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in recs:
        if r.get("answer") is None:
            continue
        try:
            r["parsed"], r["parse_usage"] = parse_answer(task, r["answer"], parse_model)
            r["parse_model"] = parse_model
            r.pop("parse_error", None)
        except Exception as e:  # noqa: BLE001
            r["parsed"], r["parse_error"] = None, str(e)[:300]
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    print(f"다시 파싱 {len(recs)}줄 → {out.name}")


if __name__ == "__main__":
    main()
