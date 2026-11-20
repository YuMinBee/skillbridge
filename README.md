# 역량다리 (SkillBridge) · 06팀

> 웹 Claude에 "내 역량 분석하고 과제 추천해 줘"라고 하면 답은 그럴듯합니다. 그런데 맞는지 확인하는 일은 취준생 몫입니다.
> 역량다리는 **같은 Claude 모델을 AWS 안에서 시스템으로 돌려**, 모든 판정에 원문 근거를 붙이고, 근거가 없으면 추천하지 않습니다.

자기소개서·포트폴리오·CV·노션·GitHub를 올리면 **STAR 강점 진단 → 실제 채용 공고 기준 부족 역량 → 고용24 교육과정과 구체적인 과제**를 근거와 함께 보여 줍니다.

- **시연 주소**: https://fazwtcf7omav34gdiahcgvds3m0zyafv.lambda-url.ap-northeast-2.on.aws/ (시연용 합성 자소서: [docs/pivot/captures/demo_resume.md](docs/pivot/captures/demo_resume.md))
- 대회: KOSA × AWS AI 부트캠프 해커톤 · 주제: AWS 클라우드 기반 채용시장 기술역량 자동 분석 및 교육과정 추천 AI 에이전트
- 팀: 변유민(팀장) · 김채희 · 김승제 · 이승연 · 제출 2026-11-22

## 숫자로 본 결과

같은 Claude Sonnet 4.6에 같은 경험 단락 60개를 5번씩 넣었습니다(평가용 test, 마지막에 한 번만 실행). 값은 사람 정답 대비, `[95% 신뢰구간]`. 전체: [eval/trust/report.md](eval/trust/report.md)

| 지표 | **역량다리** | 웹 ① 그냥 묻기 | 웹 ② 잘 쓴 프롬프트 | 웹 ③ 우리 칸 기준까지 준 프롬프트 |
|---|---|---|---|---|
| STAR 칸 정확도 | **96.2%** [93.8, 98.8] | 80.9% | 82.6% | 94.7% (차이 유의하지 않음) |
| 원문에 없는 근거를 '있다'고 한 비율 ↓ | **2.1%** [0.0, 4.5] | 35.5% | 29.1% | 6.7% |
| 5번 넣어 모두 같은 판정 | **100%** | 61.7% | 86.7% | 88.3% |

- 사람 평가자 두 명끼리의 일치도는 89.2%(κ 0.78)입니다. 위 차이 중 웹 ③과의 정확도 차이만 신뢰구간이 0을 포함합니다. 판정 자체는 프롬프트로 따라올 수 있지만, **원문에 없는 근거를 걸러 내고 매번 같은 결과를 내는 것은 시스템**에서 나옵니다.
- 실제 claude.ai에 시연 자소서를 6번(팀원 2명 × 3번) 넣어 본 결과: 강점 판단은 6번 모두 우리와 같았고 지어낸 성과도 없었습니다. 대신 추천 교육과정이 매번 달랐고, 지금 신청할 수 있는 과정을 개강일까지 준 답은 1번이었습니다. [docs/pivot/captures/web_compare.md](docs/pivot/captures/web_compare.md)

| 다른 검증 | 결과 | 근거 |
|---|---|---|
| 교육 검색: 임베딩 4종 비교 (질의 40개, nDCG@5) | 키워드 0.65 → **Cohere Embed v4 0.82** (차이 +0.18, 구간 0.08~0.28 유의) | [report_retrieval.md](eval/trust/report_retrieval.md) |
| 검색 판정을 사람이 다시 판정 (30쌍) | Sonnet 판정과 일치 76.7%, κ 0.65 | [judge_human_result.json](eval/trust/judge_human_result.json) |
| '맞는 과정 없음' 기준 | 유사도 0.35 미만이면 추천 안 함 (관련 과정을 잃지 않는 구간에서 결정) | [abstain_threshold.py](eval/trust/abstain_threshold.py) |
| 과제 구체화 (자소서 5개) | 16개 중 16개 원문 대조 통과, 같은 입력 23/23 같은 과제 | [results_tasks.json](eval/trust/results_tasks.json) |
| 배포 주소 점검 (입력 14종) | 정상 입력 분석, 이상한 입력은 이유와 함께 거절 | [eval/smoke_deploy.md](eval/smoke_deploy.md) |
| 취준생 설문 29명 | 모르는 기술은 생성형 AI로 확인 86% · AI 추천을 믿으려면 '근거 공고 문장' 45%, '추천 이유' 45%, '불확실 표시' 28% | [eval/survey_needs.md](eval/survey_needs.md) |

## 무엇을 하나

1. **강점 진단 (STAR)**: 기업 역량면접(행동사건면접)의 표준인 상황·과제·행동·결과로 경험을 나눕니다. Claude는 칸마다 **자소서 원문 문장을 고르기만** 하고, 원문에 없는 문장은 코드가 버립니다. 점수와 수준(강함·보통·약함)은 공개된 규칙 상수로만 계산합니다.
2. **강점 직군과 부족한 역량**: 지원 분야(민간 기업/공공기관)를 고르면 그쪽 실제 공고에서 자주 요구하는 역량과 비교합니다. 부족한 역량마다 공고 원문과 "민간 기업 공고 45건 중 6건이 AWS 요구" 같은 건수가 붙습니다.
3. **교육과정과 과제**: 고용24 정보기술 과정 1,856개에서 벡터 검색으로 과정을 찾고(유사도가 낮으면 "맞는 과정 없음"), 과제는 Claude가 공고 문장과 내 자소서 문장을 인용해 씁니다. 인용과 숫자가 원문에 없으면 템플릿으로 돌아갑니다.
4. **검증과 비용**: 내보내기 전에 인용 ⊂ 원문, 과정 ⊂ 고용24 목록, 추천마다 근거 1개 이상을 확인합니다. 단계마다 토큰과 금액을 계산하고 요청 예산($0.30)을 넘으면 남은 단계는 규칙으로 처리합니다. 분석 1건 약 $0.03~0.18.

## 구조 (AWS)

```
브라우저 ─ Lambda 함수 URL ─ FastAPI ─ 작업 접수(DynamoDB, 24시간) ─ Lambda 자기 호출(비동기)
                                                  │
                     슈퍼바이저: collect(GitHub README) → guard → star → skills → retriever → recommend → verifier → cost
                                    │         │        │          │            │            │
                       Bedrock Guardrails  Claude    Claude     공고 기준      Cohere v4     규칙
                         + 정규식          Sonnet 4.6 Sonnet ·   (민간/공공)    벡터 검색
                                                     Haiku 4.5              + Claude 과제
```

- **Amazon Bedrock**: Claude Sonnet 4.6(STAR·역량 추출·과제), Claude Haiku 4.5(정규화), Titan Text Embeddings v2(스킬), Cohere Embed v4(교육 검색), Guardrails(개인정보 가림)
- **AWS Lambda** 함수 URL + 자기 호출 비동기 작업(창을 닫아도 서버에서 끝까지), **DynamoDB**(작업·캐시·샌드박스, TTL), **S3·Glue·Athena**(공고 집계), CloudFormation(`infra/template.yaml`)
- 상시 과금 리소스 없음(OpenSearch Serverless 대신 파일 벡터·S3 Vectors). 모든 리소스 `project=kosa06` 태그
- 같은 문서는 24시간 같은 결과(입력 해시를 키로 DynamoDB 캐시, 원문은 저장하지 않음)

## 데이터

| 데이터 | 출처 | 규모 |
|---|---|---|
| 민간 기업 공고 | 고용24 공채속보 API + 기업 공식 채용 페이지 직접 수집([규칙](seed/market/direct_it.md)) + 공개 공고 재구성 | 백엔드 45 · AI 29 · 데이터 22건 이상 |
| 공공기관 공고 | 잡알리오 공공기관 채용정보 API (정보통신) | 백엔드 174 · AI 29 · 데이터 60건 |
| 교육과정 | 고용24 훈련과정 API, NCS 정보기술, 개강 예정만 | 1,856개 |
| 평가 정답셋 | 합성 경험 단락(유형 6가지), 사람 1·2차 라벨 | 90개 (개발 30 · 평가 60) |

## 한계 (먼저 밝힙니다)

- 평가 단락과 과제 확인용 자소서는 **합성**입니다. 정답 초안은 Claude가 쓰고 사람이 검토했습니다(그래서 2차 라벨과 웹 ③을 함께 냈습니다). 실제 자소서에서는 숫자가 낮을 수 있습니다.
- 숫자 비교는 claude.ai가 아니라 Bedrock의 같은 모델로 했습니다. 웹 답의 '부분적으로 있음'은 '있음'으로 셌습니다.
- 민간 공고는 직군별 수십 건입니다(화면에 건수 표시, 15건 미만 직군은 강점 직군 순위에서 제외). 공고 요구 역량은 사전 기반으로 뽑습니다.
- 교육과정 수준(입문/심화)은 맞추지 않습니다. 합격 여부는 예측하지 않으며, 채용 합불 판단에 쓰지 않습니다.

## 지킨 것

이력서 원문은 저장하지 않습니다(결과만 24시간) · 모델에 보내기 전 개인정보를 가립니다 · 점수는 규칙으로만, LLM은 근거 인용과 설명만 · 교육과정 이름을 지어내지 않습니다(고용24 목록만) · 모든 숫자에 95% 신뢰구간, 유의하지 않은 차이는 차이라고 말하지 않습니다 · 평가셋에 맞춰 튜닝하지 않습니다(개발/평가 분리, 평가는 한 번만).

## 실행

필요: Python 3.10+, Node 18+

```powershell
.\tasks.ps1 setup     # .venv, npm install, .env 생성 (.env.example 복사)
.\tasks.ps1 run       # API :8010 + 웹 :5173
.\tasks.ps1 test      # pytest (CI와 같음)
```

- `BEDROCK_MOCK=1`(기본)이면 AWS 없이 규칙으로 동작합니다. `0`이면 Bedrock을 부르고, 실패한 단계만 규칙으로 돌아갑니다(`aws sso login --profile kosa`).
- 평가 재현: `python eval/trust/run_ours.py --split dev` → `python eval/trust/run_compare.py --split dev`
- 배포: `python infra/deploy.py --yes` · 배포 점검: `python scripts/smoke_deploy.py`

## 폴더

| 경로 | 내용 |
|---|---|
| `backend/app/agents/` | 슈퍼바이저, STAR, 과제 구체화, 검증, 비용 |
| `backend/app/rag/` | 임베딩·벡터/BM25 검색 |
| `backend/app/routers/analyze.py` | 분석 작업 API (`/api/analyze/docs`, `/api/jobs/{id}`) |
| `frontend/src/tabs/Analyze.jsx` | 역량 분석 화면 |
| `eval/trust/` | 정답셋, 웹 비교, 검색 실험, 판정, 보고서 |
| `collectors/`, `seed/` | 공고·교육과정 수집기와 데이터 |
| `infra/` | CloudFormation, 배포 스크립트 |
| `docs/` | 발표 대본([DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)), 계획, 웹 캡처 비교 · 설계 결정과 이유: [DECISIONS.md](DECISIONS.md) |

> 11-17 멘토링 이후 주제를 바꿨습니다(기업 등록 실무 기준 → 근거로 답하는 역량 진단). 이전 버전 설명은 [docs/README_v1_이전주제.md](docs/README_v1_이전주제.md)에 남겨 두었고, 이전 화면(시장 분석·기업 콘솔)은 주소 뒤 `#market`, `#corp`로만 열립니다.
