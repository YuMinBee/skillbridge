# T4 화면·시연 — 이승연

## 목표
한 화면에서 **질문 → 진행 상태 → 인용 달린 답(또는 "근거 없음") → 근거 원문 → 비용**이 보이고, 다른 화면에서 **신뢰도 비교표**가 보이게 한다. 기능은 늘리지 않는다.

## 만들 것
1. `frontend/src/tabs/Ask.jsx`(새 기본 탭)
   - 질문 입력(선택: 이력서, 직군). 보내면 `job_id`를 localStorage에 저장하고 2초마다 `GET /api/jobs/{id}`를 부른다.
   - 진행 상태: 슈퍼바이저 → 검색 → 검증 → 비용 단계가 하나씩 켜진다. 탭을 닫았다 열어도 이어진다.
   - 답: 문장마다 `[1]` 인용. 누르면 오른쪽에 근거 원문(`quote`)과 출처 링크가 뜬다. `grounded:false` 문장은 표시를 다르게 한다.
   - `abstained`면 "근거가 없어 답하지 않았습니다"와 이유를 크게 보여 준다. 실패가 아니라 **기능**으로 보이게 한다.
   - 비용 줄: 토큰·$·단계별 막대.
2. `frontend/src/tabs/Trust.jsx`: `results_generation.json`·`results_retrieval.json`을 읽어 LLM 단독 / 단순 RAG / 우리 방식 비교표와 구간을 보여 준다. 유형(C1~C7)별로 볼 수 있게 한다.
3. 기존 탭: 기업 콘솔·시뮬레이터는 숨긴다(코드는 남김). 취준생 진단은 Ask 안의 "이력서로 진단" 흐름으로 줄이거나 뒤로 보낸다.
4. 시연 영상 `docs/demo.mp4`, 설문 `eval/SURVEY.md`.

## 백엔드 없이 시작하기
`docs/pivot/fixtures/job_running.json`, `job_done.json`, `job_abstained.json`, `results_generation.json`을 그대로 써서 화면부터 만든다. API가 생기면 주소만 바꾼다.

## Claude에게 줄 첫 지시
```
너는 T4 담당이다. AGENTS.md, docs/pivot/PLAN.md, docs/pivot/CONTRACTS.md, docs/pivot/T4_FRONTEND.md를 읽어라.
브랜치 t4-frontend에서 작업한다. CONTRACTS.md 6절의 T4 파일만 고친다.
docs/pivot/fixtures의 JSON으로 Ask 탭(진행 상태·인용·근거 패널·거부 화면·비용)을 먼저 만들어라.
```
