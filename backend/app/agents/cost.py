"""비용 에이전트. CallLog(모델·토큰) × 단가(config.PRICES) → 요청 비용, 단계별 비용, 예산 확인, 월 비용 추정."""
from .. import config


def price_of(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for key, p in config.PRICES.items():
        if key in m:
            return p
    return config.PRICES["sonnet"]


def usd(call: dict) -> float:
    pin, pout = price_of(call.get("model", ""))
    return (call.get("in", 0) * pin + call.get("out", 0) * pout) / 1_000_000


class Meter:
    """한 job 동안 에이전트별 호출 범위를 기록한다. log.calls[i:j]가 그 에이전트 몫."""

    def __init__(self, log, budget: float | None = None):
        self.log = log
        self.budget = config.JOB_BUDGET_USD if budget is None else budget
        self.spans: dict[str, list[tuple[int, int]]] = {}
        self._open: dict[str, int] = {}

    def start(self, agent: str):
        self._open[agent] = len(self.log.calls)

    def stop(self, agent: str):
        self.spans.setdefault(agent, []).append((self._open.pop(agent, len(self.log.calls)), len(self.log.calls)))

    def total(self) -> float:
        return sum(usd(c) for c in self.log.calls)

    def over_budget(self) -> bool:
        return self.total() >= self.budget

    def summary(self) -> dict:
        calls = self.log.calls
        by = {a: round(sum(usd(c) for i, j in sp for c in calls[i:j]), 6) for a, sp in self.spans.items()}
        return {"input_tokens": sum(c.get("in", 0) for c in calls), "output_tokens": sum(c.get("out", 0) for c in calls),
                "usd": round(self.total(), 6), "by_agent": by, "budget_usd": self.budget,
                "calls": len(calls)}


def monthly(usd_per_job: float, users: int, jobs_per_user: int = 4) -> float:
    """사용자 N명이 한 달에 jobs_per_user번씩 분석할 때 Bedrock 비용(USD). 상시 과금 리소스는 없다."""
    return round(usd_per_job * users * jobs_per_user, 2)
