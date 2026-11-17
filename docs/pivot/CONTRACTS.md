# 트랙 간 계약 (인터페이스)

> 네 트랙이 서로를 기다리지 않도록, 주고받는 모양을 먼저 고정한다. 바꾸려면 이 파일만 고치는 작은 PR을 올리고 팀 채팅에 알린다.
> 상대 트랙이 아직 없으면 `docs/pivot/fixtures/`의 예시 JSON으로 대신 개발한다.

## 1. 코퍼스 문서 (T3 → T2)

`seed/corpus/*.jsonl`, 한 줄에 문서 하나.

```json
{"doc_id": "ncs-2001020201-03", "kind": "ncs|job_info|course|posting",
 "title": "응용SW엔지니어링 · 요구사항 확인 · 수행준거",
 "text": "본문(원문 그대로, 요약하지 않음)",
 "source": "NCS 국가직무능력표준", "url": "https://...", "collected_at": "2026-11-18",
 "meta": {"job_family": "backend|ai_ml|data", "valid_until": "2026-12-31 또는 null"}}
```

## 2. 검색 (T2 → T1)

`backend/app/rag/retrieve.py`

```python
def search(query: str, k: int = 5, *, config: str = "best", filters: dict | None = None,
           log: CallLog | None = None) -> list[dict]:
    """→ [{"chunk_id", "doc_id", "text", "score", "kind", "title", "url"}], 점수 내림차순."""
```

- `config`는 실험 조합 이름이다(예: `"t2v-512_c300_hybrid_rerank"`). `"best"`는 T2가 확정한 조합.
- Bedrock 호출은 반드시 `log`에 남긴다(비용 계산용).

## 3. 작업(job)과 답변 (T1 → T4)

`POST /api/ask` `{"question": "...", "resume": "선택", "job_family": "선택"}` → `{"job_id": "j_..."}`

`GET /api/jobs/{job_id}` →

```json
{"job_id": "j_123", "status": "queued|running|done|failed",
 "case": "C1", "progress": [{"agent": "retriever", "status": "done", "ms": 820}],
 "answer": {"text": "문장마다 [1] 같은 인용 번호", "abstained": false,
            "abstain_reason": null,
            "sentences": [{"text": "...", "cites": [1], "grounded": true}]},
 "citations": [{"n": 1, "doc_id": "...", "title": "...", "url": "...", "quote": "근거 문장"}],
 "cost": {"input_tokens": 0, "output_tokens": 0, "usd": 0.0,
          "by_agent": {"supervisor": 0.0, "retriever": 0.0, "verifier": 0.0}},
 "trace": [{"agent": "...", "model": "...", "ms": 0, "in": 0, "out": 0}]}
```

- `abstained: true`이면 `text`는 왜 답하지 않는지 설명하고 `citations`는 비어 있을 수 있다.
- 브라우저는 `job_id`를 localStorage에 두고 2초마다 조회한다. 닫았다 열어도 이어서 본다.

## 4. 평가 정답 (T3 → T2·T1)

`eval/rag/gold_dev.jsonl` (T2가 봐도 됨), `eval/rag/gold_test.jsonl` (T3만 연다. 마지막 1회 실행).

```json
{"qid": "q001", "case": "C1", "question": "...",
 "gold_doc_ids": ["ncs-..."], "must_include": ["핵심 사실 1", "핵심 사실 2"],
 "should_abstain": false, "note": "판정 기준 메모"}
```

## 5. 평가 결과 (T2·T3 → T4)

`eval/rag/results_retrieval.json`, `eval/rag/results_generation.json`.

```json
{"_meta": {"at": "...", "n": 100, "split": "test"},
 "systems": {"llm_only": {"faithfulness": [0.0, 0.0, 0.0]}, "naive_rag": {}, "ours": {}}}
```

수치는 `[값, 구간 하한, 구간 상한]`(95% 부트스트랩)이다. 화면은 구간을 그대로 보여 준다.

## 6. 파일 소유 (충돌 방지)

| 트랙 | 혼자 고치는 곳 |
|---|---|
| T1 | `backend/app/agents/**`, `backend/app/routers/ask.py`, `backend/app/adapters/jobs.py`, `infra/template.yaml`, `docs/pivot/PLAN.md` |
| T2 | `backend/app/rag/**`, `infra/build_kb.py`, `eval/rag/run_retrieval.py`, `eval/rag/cache/`(gitignore) |
| T3 | `collectors/**`, `seed/corpus/**`, `eval/rag/gold_*.jsonl`, `eval/rag/metrics.py`, `eval/rag/run_generation.py`, `eval/rag/report.md` |
| T4 | `frontend/**`, `docs/demo.mp4`, `eval/SURVEY.md` |
| 공유(작은 PR + 알림) | `AGENTS.md`, `docs/pivot/CONTRACTS.md`, `requirements.txt`, `backend/app/config.py`, `backend/app/main.py`(라우터 등록 한 줄) |
