# 트랙 간 계약 (인터페이스)

> 네 트랙이 서로 기다리지 않도록 주고받는 모양을 먼저 고정한다. 바꾸려면 이 파일만 고치는 작은 PR + 팀 채팅 알림.
> 상대 트랙이 아직 없으면 `docs/pivot/fixtures/` 예시 JSON이나 임시 구현으로 진행한다.

## 1. 코퍼스 문서 (T3 → T2)

`seed/corpus/*.jsonl`, 한 줄에 문서 하나. 본문은 요약하지 않고 원문 그대로.

```json
{"doc_id": "ncs-2001020201-03", "kind": "ncs_unit|ncs_basic|course|posting|rubric",
 "title": "응용SW엔지니어링 · 요구사항 확인 · 수행준거",
 "text": "원문", "source": "NCS 국가직무능력표준", "url": "https://...",
 "collected_at": "2026-11-18", "meta": {"job_family": "backend|ai_ml|data", "ncs_code": "..."}}
```

## 2. STAR 강점 진단 (T1 내부, T3 평가·T4 화면이 읽음)

`backend/app/agents/star.py`

```python
def diagnose(resume: str, *, log: CallLog | None = None) -> list[dict]
```

```json
[{"exp_id": "e1", "title": "팀 프로젝트: 식당 예약 API",
  "slots": {"S": {"quote": "원문 그대로", "present": true},
            "T": {"quote": null, "present": false},
            "A": {"quote": "...", "present": true},
            "R": {"quote": "...", "present": true, "quantified": true}},
  "my_role_clear": true,
  "score": 3.5, "level": "strong|ok|weak",
  "competencies": ["problem_solving", "backend_api"],
  "missing_hint": "T(맡은 과제)가 드러나지 않음"}]
```

- `quote`는 반드시 이력서 원문의 부분 문자열이다. 원문에서 못 찾으면 `present:false`로 바꾼다(코드로 강제).
- `score`·`level`은 규칙으로만 계산한다(칸 수, 수치 성과, 내 역할). 규칙은 `star.py` 상단 상수로 공개한다.

## 3. 검색 (T2 → T1)

`backend/app/rag/retrieve.py`

```python
def search(query: str, k: int = 5, *, kinds: list[str] | None = None, job_family: str | None = None,
           config: str = "best", log: CallLog | None = None) -> list[dict]
# → [{"chunk_id","doc_id","kind","title","url","text","score"}], 점수 내림차순
```

## 4. 과제 추천 (T2 → T1)

`backend/app/agents/recommend_task.py`

```python
def recommend(gaps: list[dict], star: list[dict], job_family: str, *, log=None) -> list[dict]
```

```json
[{"rank": 1, "target": "ncs:요구사항 확인" , "why": "갭/STAR 빈칸 설명 [1]",
  "task": "증명 과제 설명 [2]", "course": {"id": "고용24 과정 ID", "name": "카탈로그 이름 그대로", "hours": 40, "url": "..."},
  "cites": [1, 2], "abstained": false}]
```

- `course.name`은 카탈로그에 있는 값만. 맞는 과정이 없으면 `course: null`, 과제만 낸다.
- 근거를 못 찾으면 `abstained: true`와 이유.

## 5. 작업(job) (T1 → T4)

`POST /api/analyze` `{"resume": "...", "job_family": "backend|ai_ml|data", "posting": "선택"}` → `{"job_id": "j_..."}`

`GET /api/jobs/{job_id}` →

```json
{"job_id": "j_123", "status": "queued|running|done|failed",
 "progress": [{"agent": "star", "status": "done", "ms": 2100}],
 "result": {"strengths": [/* 2절 */], "gaps": [{"id": "...", "name": "...", "status": "own|part|verify|miss", "cites": [3]}],
            "recommendations": [/* 4절 */], "readiness": {"apply": 72, "practice": 58}},
 "citations": [{"n": 1, "kind": "resume|ncs_unit|course|posting", "doc_id": "...", "title": "...", "url": "...", "quote": "..."}],
 "cost": {"input_tokens": 0, "output_tokens": 0, "usd": 0.0, "by_agent": {"star": 0.0}},
 "trace": [{"agent": "...", "model": "...", "ms": 0, "in": 0, "out": 0}]}
```

- 브라우저는 `job_id`를 localStorage에 두고 2초마다 조회한다. 이력서 원문은 job에 저장하지 않는다(규칙 7). 인용 문장만 남긴다.

## 6. 평가 (T3)

정답셋 (`eval/trust/`)
- `gold_star_dev.jsonl` / `gold_star_test.jsonl`: `{"id","text","case":"full|no_R|no_T|inflated|team_vague|short","slots":{"S":true,...},"quantified":bool,"labeler":"A"}` (2차 라벨은 `labeler:"B"`)
- `gold_reco_dev.jsonl` / `gold_reco_test.jsonl`: `{"id","resume","job_family","acceptable_targets":["ncs:..."],"note"}`
- test 파일은 T3만 연다. 마지막에 한 번 돌린다(규칙 9).

결과 `eval/trust/results.json` (T4 신뢰도 화면이 읽음)

```json
{"_meta": {"at": "...", "split": "test", "n": {"star": 80, "reco": 30}},
 "metrics": {"star_slot_acc": {"web": [0,0,0], "ours": [0,0,0], "human_ab": [0,0,0]},
             "fake_evidence_rate": {"web": [], "ours": []},
             "fake_course_rate": {"web": [], "ours": []},
             "consistency_5runs": {"web": [], "ours": []},
             "inflated_false_strong": {"web": [], "ours": []}},
 "retrieval": {"configs": {"t2v512_c300_hybrid": {"recall@5": [], "mrr": [], "p95_ms": 0, "usd_per_1k": 0}}}}
```

## 7. 파일 소유 (충돌 방지)

| 트랙 | 혼자 고치는 곳 |
|---|---|
| T1 | `backend/app/agents/{supervisor,star,verifier,cost}.py`, `backend/app/adapters/jobs.py`, `backend/app/routers/analyze.py`, `infra/template.yaml`, `docs/pivot/PLAN.md`, `docs/DEMO_SCRIPT.md` |
| T2 | `backend/app/rag/**`, `backend/app/agents/{retriever,recommend_task}.py`, `infra/build_kb.py`, `eval/trust/run_retrieval.py`, `eval/trust/cache/`(gitignore) |
| T3 | `collectors/**`, `seed/corpus/**`, `eval/trust/gold_*.jsonl`, `eval/trust/LABELING.md`, `eval/trust/metrics.py`, `eval/trust/run_compare.py`, `eval/trust/baseline_web.py`, `eval/trust/report.md` |
| T4 | `frontend/**`, `docs/demo.mp4`, `eval/SURVEY.md`, `docs/pivot/captures/`(웹 Claude 캡처) |
| 공유(작은 PR + 알림) | `AGENTS.md`, `docs/pivot/CONTRACTS.md`, `requirements.txt`, `backend/app/config.py`, `backend/app/main.py`(라우터 등록 한 줄), `backend/app/agents/__init__.py` |
