# T1 STAR 강점 진단 · 슈퍼바이저 · 검증 · 비용 · 작업(job) · 발표 — 변유민

## 목표
이력서를 넣으면 job으로 접수하고, 슈퍼바이저가 ① STAR 강점 진단 → ② 역량 연결 → ③ 과제 추천을 돌려 **모든 판정에 원문·NCS·과정 인용이 붙은 결과**를 낸다. 단계별 비용을 남기고, 브라우저를 닫아도 끝까지 돈다.

## 구현 목록 (순서대로)

| # | 파일 | 할 일 | 완료 기준 |
|---|---|---|---|
| 1 | `agents/star.py` | 경험 단락 분리 → Converse 구조화 출력(Sonnet)으로 S·T·A·R 칸 + 원문 인용 → `_locate`로 인용 검증(없으면 `present:false`) → 규칙 점수 | [CONTRACTS 2절](CONTRACTS.md) 모양, MOCK 모드는 규칙(문장 패턴)으로 동작 |
| 2 | `agents/star.py` 규칙 | 점수 = 칸 수(S·T·A·R 각 1) + 수치 성과 0.5 + 내 역할 명확 0.5 − 꾸민 말만 있고 A 없음이면 상한 1. 상수로 공개, `DECISIONS.md`에 이유 | 테스트: 꾸민 말 문장 → `weak` |
| 3 | `adapters/jobs.py`, `routers/analyze.py` | `POST /api/analyze` → job_id, `GET /api/jobs/{id}`. 저장은 기존 `storage`에 `JOB#`(TTL 24시간). 로컬은 스레드, 배포는 Lambda 자기 비동기 호출 | 브라우저 없이 curl로 끝까지 돈다 |
| 4 | `agents/supervisor.py` | 단계 계획·실행·폴백. ②는 기존 `diagnose`의 규칙 점수 재사용(직군 기준은 T2 검색 결과의 NCS로) | 한 단계가 실패해도 나머지 결과는 나온다 |
| 5 | `agents/verifier.py` | 결과의 모든 문장에 인용 번호 → 인용 내용이 실제로 있는지 확인. Guardrails contextual grounding도 가능하면. 실패 시 1회 재작성 → 그래도 실패면 `abstained` | 테스트: 지어낸 인용 → 제거됨 |
| 6 | `agents/cost.py` | `CallLog` 집계 × 모델 단가(`config.py` 상수, 출처 링크 주석) → `cost`. 요청 예산 초과 시 남은 LLM 단계 생략 | trace 합 = cost 합 |
| 7 | `tests/test_agents.py` | 위 기준들 | 기존 80개 + 새 테스트 통과 |
| 8 | 발표 | `docs/DEMO_SCRIPT.md`, 슬라이드 8장 | PLAN 2절 순서 |

## 지킬 것
- 점수는 규칙으로만. LLM은 칸 채우기(인용)와 설명만(규칙 8).
- 이력서 원문은 job에 저장하지 않는다. 인용 문장만(규칙 7).

## Claude에게 줄 첫 지시
```
너는 T1 담당이다. AGENTS.md, docs/pivot/PLAN.md, docs/pivot/CONTRACTS.md, docs/pivot/T1_SUPERVISOR.md를 읽어라.
브랜치 t1-supervisor에서 작업한다. CONTRACTS.md 7절의 T1 파일만 고친다.
구현 목록 1→3 순서로, BEDROCK_MOCK=1에서 POST /api/analyze → GET /api/jobs/{id}가 fixtures/job_done.json 모양으로 돌게 하고 테스트를 붙여라.
```
