"""STAR 평가 지표 (웹 방식 vs 우리 방식). PLAN 4절, CONTRACTS 6절.

모든 지표는 [값, 95% 구간 하한, 상한]. 구간은 **경험 단락(id) 단위 부트스트랩**이다.
같은 단락의 5회 반복은 서로 독립이 아니므로 반복이 아니라 단락을 다시 뽑는다.
두 방식의 차이는 같은 id 표본으로 둘 다 계산하는 대응(paired) 부트스트랩이다.

예측은 먼저 같은 모양으로 바꾼다(norm_web / norm_ours).
  {"slots": {"S": bool, ...}, "claims": {"S": str|None, ...}, "quantified": bool|None, "overall": str}

지표 정의 (판정은 전부 규칙, LLM 채점 없음)
- slot_acc       : S·T·A·R 칸 유무가 정답과 같은 비율. 단락마다 (4칸 × 반복) 평균 → 단락 평균.
- slot_kappa     : 같은 판정들을 모아 Cohen κ (우연 일치를 뺀 값).
- fake_evidence  : 정답이 '없음'인 칸(+ 수치 성과가 없는 결과)을 '있다'고 한 비율.
                   = 이력서에 없는 경험·성과를 있다고 한 비율. 분모는 정답 '없음' 판정 수.
- consistency    : 같은 단락을 5번 넣어 5번 모두 같은 S·T·A·R 판정이 나온 단락 비율.
- inflated_strong: 꾸민 말 단락(case=inflated)에 '강점이 강하다(strong)'고 한 비율. 낮을수록 좋다.
- quote_verbatim : (참고) '있다'고 한 칸의 근거 문장이 원문에 글자 그대로 있는 비율.
                   plain 웹 방식은 인용을 요구하지 않았으므로 낮은 게 당연하다. 핵심 지표로 쓰지 않는다.
"""
import random
import re

SLOTS = ("S", "T", "A", "R")
N_BOOT = 2000
SEED = 20261118

# 웹 답변 파싱 결과(baseline_web.py STAR_SCHEMA) → 있다/없다
#  weak(있긴 한데 부족) = 있다고 본 것. unmentioned(언급 안 함) = 있다고 하지 않은 것.
WEB_PRESENT = {"present": True, "weak": True, "absent": False, "unmentioned": False}


# ── 예측 정규화 ───────────────────────────────────────────────────────
def norm_web(rec: dict) -> dict | None:
    p = rec.get("parsed")
    if not p:
        return None  # 답변 실패·파싱 실패 → 결측(보고서에 개수 표시)
    return {"slots": {k: WEB_PRESENT.get((p.get(k) or {}).get("status"), False) for k in SLOTS},
            "claims": {k: (p.get(k) or {}).get("claim") for k in SLOTS},
            "quantified": p.get("quantified"),
            "overall": p.get("overall") or "unclear"}


def norm_ours(rec: dict) -> dict | None:
    """rec["result"] = star.diagnose() 반환값(경험 목록). 정답 단락 하나가 여러 경험으로 나뉘면 칸을 합친다(하나라도 있으면 있음)."""
    exps = rec.get("result")
    if exps is None:
        return None
    slots = {k: False for k in SLOTS}
    claims = {k: None for k in SLOTS}
    quant, levels = None, []
    for e in exps:
        for k in SLOTS:
            s = (e.get("slots") or {}).get(k) or {}
            if s.get("present"):
                slots[k] = True
                claims[k] = claims[k] or s.get("quote")
        r = (e.get("slots") or {}).get("R") or {}
        if r.get("present"):
            quant = bool(quant) or bool(r.get("quantified"))
        elif quant is None:
            quant = False
        levels.append(e.get("level"))
    order = ["strong", "ok", "weak"]
    overall = next((lv for lv in order if lv in levels), "unclear")
    return {"slots": slots, "claims": claims, "quantified": quant, "overall": overall}


def norm_human(row: dict) -> dict:
    """2차 라벨(gold_star_b.jsonl) 한 줄 → 예측 모양."""
    return {"slots": {k: bool(row["slots"].get(k)) for k in SLOTS}, "claims": {k: None for k in SLOTS},
            "quantified": row.get("quantified"), "overall": "unclear"}


# ── 지표: ids(중복 허용, 부트스트랩 표본) → 값 ────────────────────────────
def slot_acc(gold: dict, preds: dict, ids: list) -> float | None:
    per = []
    for i in ids:
        runs = preds.get(i) or []
        if not runs:
            continue
        hits = [p["slots"][k] == gold[i]["slots"][k] for p in runs for k in SLOTS]
        per.append(sum(hits) / len(hits))
    return sum(per) / len(per) if per else None


def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def slot_kappa(gold: dict, preds: dict, ids: list) -> float | None:
    return kappa([(gold[i]["slots"][k], p["slots"][k]) for i in ids for p in (preds.get(i) or []) for k in SLOTS])


def fake_evidence(gold: dict, preds: dict, ids: list) -> float | None:
    num = den = 0
    for i in ids:
        g = gold[i]
        for p in preds.get(i) or []:
            for k in SLOTS:
                if not g["slots"][k]:
                    den += 1
                    num += p["slots"][k]
            if g.get("quantified") is False and p.get("quantified") is not None:
                den += 1
                num += bool(p["quantified"])
    return num / den if den else None


def slot_vec(p: dict) -> tuple:
    return tuple(p["slots"][k] for k in SLOTS)


def consistency(preds: dict, ids: list, k: int = 5) -> float | None:
    vals = []
    for i in ids:
        runs = preds.get(i) or []
        if len(runs) < k:
            continue
        vals.append(len({slot_vec(p) for p in runs[:k]}) == 1)
    return sum(vals) / len(vals) if vals else None


def inflated_strong(gold: dict, preds: dict, ids: list) -> float | None:
    num = den = 0
    for i in ids:
        if gold[i].get("case") != "inflated":
            continue
        for p in preds.get(i) or []:
            den += 1
            num += p["overall"] == "strong"
    return num / den if den else None


_WS = re.compile(r"\s+")


def _found(claim: str, text: str) -> bool:
    c = _WS.sub("", (claim or "").strip().strip("\"'“”‘’「」『』"))
    return len(c) >= 4 and c in _WS.sub("", text)


def quote_verbatim(gold: dict, preds: dict, ids: list) -> float | None:
    num = den = 0
    for i in ids:
        for p in preds.get(i) or []:
            for k in SLOTS:
                if p["slots"][k] and p["claims"].get(k):
                    den += 1
                    num += _found(p["claims"][k], gold[i]["text"])
    return num / den if den else None


METRICS = {
    "star_slot_acc": slot_acc,
    "star_slot_kappa": slot_kappa,
    "fake_evidence_rate": fake_evidence,
    "consistency_5runs": lambda g, p, ids: consistency(p, ids),
    "inflated_false_strong": inflated_strong,
    "quote_verbatim_rate": quote_verbatim,
}
LOWER_IS_BETTER = {"fake_evidence_rate", "inflated_false_strong"}


# ── 부트스트랩 ────────────────────────────────────────────────────────
def _pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _r(x):
    return None if x is None else round(x, 4)


def boot(fn, gold: dict, preds: dict, ids: list, n: int = N_BOOT, seed: int = SEED) -> list:
    """[값, 하한, 상한]. 계산할 수 없으면 [None, None, None]."""
    est = fn(gold, preds, ids)
    if est is None:
        return [None, None, None]
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        s = [rng.choice(ids) for _ in ids]
        v = fn(gold, preds, s)
        if v is not None:
            vals.append(v)
    if not vals:
        return [_r(est), None, None]
    return [_r(est), _r(_pct(vals, 0.025)), _r(_pct(vals, 0.975))]


def boot_diff(fn, gold: dict, preds_a: dict, preds_b: dict, ids: list, n: int = N_BOOT, seed: int = SEED) -> list:
    """a − b 의 [값, 하한, 상한]. 같은 id 표본으로 둘 다 계산(대응)."""
    a, b = fn(gold, preds_a, ids), fn(gold, preds_b, ids)
    if a is None or b is None:
        return [None, None, None]
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        s = [rng.choice(ids) for _ in ids]
        va, vb = fn(gold, preds_a, s), fn(gold, preds_b, s)
        if va is not None and vb is not None:
            vals.append(va - vb)
    if not vals:
        return [_r(a - b), None, None]
    return [_r(a - b), _r(_pct(vals, 0.025)), _r(_pct(vals, 0.975))]


def significant(ci: list) -> bool | None:
    """구간이 0을 포함하지 않으면 True (AGENTS 규칙 12)."""
    if ci[1] is None or ci[2] is None:
        return None
    return ci[1] > 0 or ci[2] < 0
