# T3 코퍼스·정답셋·생성 평가 — 김채희

## 목표
공개·공식 자료만으로 코퍼스를 만들고, **경우의 수(C1~C7)별 정답셋**을 만들어, LLM 단독 / 단순 RAG / 우리 방식을 같은 질문으로 비교한다. 발표의 핵심 표는 이 트랙에서 나온다.

## 만들 것
1. 코퍼스 `seed/corpus/*.jsonl` ([CONTRACTS 1절](CONTRACTS.md) 모양)
   - NCS 정보기술 분야 능력단위·수행준거: 공공데이터포털 API가 있는지 먼저 확인한다. 없으면 ncs.go.kr 공개 자료. 수집기는 `collectors/ncs.py`.
   - 커리어넷·워크넷 직업정보(개발자·데이터·AI 관련 직업): API 확인 → `collectors/job_info.py`.
   - 고용24 과정·잡알리오 공고: 기존 `seed/courses`, `seed/market`을 변환만 한다.
   - 키는 `.env`에만 둔다. 이름과 길이만 확인한다.
2. 정답셋 `eval/rag/gold_dev.jsonl`(30%) · `gold_test.jsonl`(70%), 합계 100문항 이상, 유형마다 15개 이상. 질문은 취준생이 실제로 물을 말투로 쓴다.
   - C3(근거 없음)·C7(없는 과정 이름)은 일부러 많이 넣는다. 신뢰도 차이가 가장 크게 나는 곳이다.
   - 라벨 규칙은 `eval/rag/LABELING.md`에 먼저 쓰고, 2차 라벨 10~20%로 κ를 낸다.
3. `eval/rag/metrics.py`: faithfulness(답의 문장 중 인용 근거로 뒷받침되는 비율), 인용 정확도, 거부 정확도(C3·C4·C7), 없는 과정 이름 생성률, `must_include` 일치율. 판정은 규칙 우선이고, LLM 판정을 쓰면 판정 모델과 프롬프트를 기록한다. 가능하면 Bedrock RAG 평가 작업 결과와 나란히 둔다.
4. `eval/rag/run_generation.py`: 세 방식(LLM 단독, 단순 RAG, 우리 방식 = T1의 `/api/ask`)을 같은 질문으로 돌리고 `results_generation.json` + `report.md`를 만든다. 95% 부트스트랩 구간을 쓰고, 구간이 0을 포함하면 "유의하지 않음"이라고 쓴다.

## 지킬 것
- 과정 이름을 지어내지 않는다(정답셋에도). 이력서 원문을 저장하지 않는다. 예시 이력서는 합성으로 만든다.
- `gold_test.jsonl`은 T2에게 주지 않는다.

## Claude에게 줄 첫 지시
```
너는 T3 담당이다. AGENTS.md, docs/pivot/PLAN.md, docs/pivot/CONTRACTS.md, docs/pivot/T3_DATA_EVAL.md를 읽어라.
브랜치 t3-data-eval에서 작업한다. CONTRACTS.md 6절의 T3 파일만 고친다.
먼저 NCS·커리어넷·워크넷 공개 API가 있는지 확인해 출처와 신청 방법을 eval/rag/SOURCES.md에 정리하고, 기존 과정·공고를 seed/corpus로 변환해라.
```
