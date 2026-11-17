# T1 슈퍼바이저·비용·작업(job) — 변유민

## 목표
질문 하나를 작업으로 받아, 슈퍼바이저가 하위 에이전트를 불러 **인용이 달린 답 또는 "근거 없음"**을 내고, 단계별 비용을 남긴다. 브라우저를 닫아도 끝까지 돈다.

## 만들 것
1. `backend/app/agents/supervisor.py`: 질문 유형 분류(C1~C7, [PLAN 4절](PLAN.md)), 계획, 하위 에이전트 호출 순서. Converse 도구 호출, 모델은 `FAST_MODEL_ID`(Haiku).
2. `backend/app/agents/{retriever,diagnose,course,verifier,cost}.py`
   - retriever: `rag.retrieve.search()`를 부른다. T2가 아직이면 `seed/corp-docs`와 과정 카탈로그를 키워드로 찾는 임시 구현을 쓴다.
   - diagnose: 기존 `pipeline/score.py`를 그대로 쓴다. 점수는 규칙으로만 낸다.
   - course: 기존 `pipeline/recommend.py`와 카탈로그를 쓴다. 카탈로그에 없는 과정 이름은 답에서 지운다.
   - verifier: 문장마다 인용 번호가 있는지, 인용한 청크에 그 내용이 있는지 확인한다. 가능하면 Bedrock Guardrails contextual grounding도 쓴다. 실패하면 한 번 다시 쓰고, 또 실패하면 `abstained`.
   - cost: `adapters/bedrock.py`의 `CallLog`를 모아 모델별 단가(`config.py`에 상수로)로 금액을 낸다. 요청 예산(예: $0.05)을 넘으면 남은 단계를 건너뛴다.
3. `backend/app/adapters/jobs.py` + `backend/app/routers/ask.py`: `POST /api/ask` → job_id, `GET /api/jobs/{id}`. 응답 모양은 [CONTRACTS 3절](CONTRACTS.md) 그대로. 저장은 기존 `storage`(SQLite/DynamoDB)에 `JOB#` 키로. 로컬은 스레드로 실행하고, 배포는 Lambda가 자기 자신을 비동기 호출한다(`InvocationType=Event`).
4. 테스트: `backend/tests/test_agents.py`. MOCK 모드로 C3(근거 없음)과 C7(없는 과정)이 반드시 `abstained`인지, 비용 합이 trace 합과 같은지 확인한다.

## 지킬 것
- 기존 테스트 80개가 계속 통과해야 한다(`.\tasks.ps1 test`).
- AWS 리소스 변경(템플릿 배포, 권한)은 팀장 승인 뒤에(본인이 팀장이지만 기록은 남긴다).

## Claude에게 줄 첫 지시
```
너는 T1 담당이다. AGENTS.md, docs/pivot/PLAN.md, docs/pivot/CONTRACTS.md, docs/pivot/T1_SUPERVISOR.md를 읽어라.
브랜치 t1-supervisor에서 작업한다. CONTRACTS.md 6절의 T1 파일만 고친다.
먼저 BEDROCK_MOCK=1로 POST /api/ask → GET /api/jobs/{id}가 fixtures/job_done.json 모양으로 돌게 만들고 테스트를 붙여라.
```
