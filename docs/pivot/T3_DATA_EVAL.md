# T3 코퍼스 · 정답셋 · 웹 방식 비교 평가 — 김채희

## 목표
**발표 3번 슬라이드의 숫자를 만든다.** 가장 급한 트랙이다. STAR 정답셋과 추천 정답셋을 만들고, 같은 이력서를 **웹 방식(같은 Claude, 프롬프트 한 번)**과 **우리 방식**에 넣어 [PLAN 4절](PLAN.md) 지표를 95% 구간으로 낸다.

## 구현 목록 (순서대로)

| # | 파일 | 할 일 | 완료 기준 |
|---|---|---|---|
| 1 | `eval/trust/LABELING.md` | STAR 칸 판정 규칙(S·T·A·R 각각 "있다"의 기준, 수치 성과, 내 역할), 예시 각 2개 | 라벨러 두 명이 이 문서만 보고 라벨 가능 |
| 2 | `eval/trust/gold_star_{dev,test}.jsonl` | 합성 경험 단락 80개 이상. case별(full·no_R·no_T·inflated·team_vague·short) 10개 이상. dev 30% / test 70% | [CONTRACTS 6절](CONTRACTS.md) 모양 |
| 3 | 2차 라벨 | 다른 팀원이 30% 이상을 따로 라벨(`labeler:"B"`). 1차 라벨을 보지 않고 | 사람 A–B κ 계산 가능 |
| 4 | `collectors/ncs.py` → `seed/corpus/ncs.jsonl` | NCS 정보기술 분야 능력단위·수행준거·직업기초능력. 공공데이터포털 API 먼저 확인, 없으면 ncs.go.kr 공개 자료. 출처는 `eval/trust/SOURCES.md` | 직군 3개(backend·ai_ml·data)에 대응하는 단위 |
| 5 | `seed/corpus/courses.jsonl` 등 | 기존 `seed/courses`·`seed/market`을 [CONTRACTS 1절](CONTRACTS.md) 모양으로 변환 | |
| 6 | `eval/trust/gold_reco_{dev,test}.jsonl` | 합성 이력서 30개 이상 × 직군. 받아들일 수 있는 추천 대상(NCS 단위) 목록 | |
| 7 | `eval/trust/baseline_web.py` | 같은 Bedrock Claude 모델에 "내 역량 분석하고 과제 추천해 줘" + 이력서. 검색·규칙·검증 없음. 결과를 STAR 칸·과정 이름으로 파싱해 저장 | 같은 입력 5회 실행 저장(일관성용) |
| 8 | `eval/trust/metrics.py`, `run_compare.py` | STAR 칸 정확도·κ, 없는 근거 생성률, 지어낸 과정 비율(카탈로그 대조), 5회 일관성, 꾸민 말 오판정률. 부트스트랩 95% 구간 | `results.json` + `report.md`. 구간이 0을 포함하면 "유의하지 않음" |
| 9 | (확인) 공개 평가 기준 | NCS 기반 면접 행동 기준 평정표 등이 공개돼 있는지. 있으면 STAR 점수 구간 근거로 T1에 전달 | `SOURCES.md`에 링크 |

## 지킬 것
- 정답셋 문장은 합성으로 만든다. 실제 이력서를 넣지 않는다. 과정 이름을 지어내지 않는다.
- test 파일은 T2에게 주지 않는다. T1·T2가 test로 튜닝하지 않게.

## Claude에게 줄 첫 지시
```
너는 T3 담당이다. AGENTS.md, docs/pivot/PLAN.md, docs/pivot/CONTRACTS.md, docs/pivot/T3_DATA_EVAL.md를 읽어라.
브랜치 t3-data-eval에서 작업한다. CONTRACTS.md 7절의 T3 파일만 고친다.
구현 목록 1→2부터: STAR 라벨 규칙 문서를 쓰고, case별 합성 경험 단락 정답셋 초안을 만들어라. 그다음 7번(웹 방식 기준선)을 만들어라.
```
