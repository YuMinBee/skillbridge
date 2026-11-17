# 작업 인수인계 (AI 코딩 도구용)

> Claude Code는 `CLAUDE.md`를, Codex는 이 파일을 자동으로 읽습니다. 사람이 읽어도 됩니다.
> 작업이 끝나면 아래 **현재 상태**와 **다음 할 일**을 갱신하고 커밋하세요. 마지막 갱신: 2026-11-16 (변유민 + Claude).

## ⚠️ 2026-11-17 전면 수정 중: 먼저 읽을 것

멘토링 후 방향을 바꿨다. **근거로 답하는 취업 역량 RAG**: 공개·공식 자료에서만 인용하고, 근거가 없으면 답하지 않으며, 그 신뢰도를 LLM 단독·단순 RAG와 비교해 숫자로 보여 준다. 기업이 입력한 기준과 기술 블로그는 더 이상 쓰지 않는다.

- 계획: [docs/pivot/PLAN.md](docs/pivot/PLAN.md) · 트랙 간 계약과 파일 소유: [docs/pivot/CONTRACTS.md](docs/pivot/CONTRACTS.md)
- 네 명이 각자 Claude Code를 돌린다. **자기 트랙 문서의 "Claude에게 줄 첫 지시"를 그대로 붙여 넣고 시작한다.**

| 트랙 | 담당 | 브랜치 | 문서 |
|---|---|---|---|
| T1 슈퍼바이저·비용·작업(job) | 변유민 | `t1-supervisor` | [T1_SUPERVISOR.md](docs/pivot/T1_SUPERVISOR.md) |
| T2 검색(RAG) 실험 | 김승제 | `t2-rag` | [T2_RAG.md](docs/pivot/T2_RAG.md) |
| T3 코퍼스·정답셋·생성 평가 | 김채희 | `t3-data-eval` | [T3_DATA_EVAL.md](docs/pivot/T3_DATA_EVAL.md) |
| T4 화면·시연 | 이승연 | `t4-frontend` | [T4_FRONTEND.md](docs/pivot/T4_FRONTEND.md) |

병렬 작업 규칙
1. 시작 전 `git pull origin main`, 자기 브랜치에서만 작업, PR로 main에 합친다. 하루 한 번 이상 main을 자기 브랜치에 merge한다.
2. **CONTRACTS.md 6절의 내 파일만 고친다.** 공유 파일(AGENTS.md, CONTRACTS.md, requirements.txt, config.py, main.py)은 그 파일만 바꾸는 작은 PR로 올리고 팀 채팅에 알린다.
3. 다른 트랙이 아직 없으면 `docs/pivot/fixtures/`나 임시 구현으로 진행한다. 기다리지 않는다.
4. 아래 "반드시 지킬 규칙"은 그대로 유효하다. 특히 키는 `.env`에만 두고, AWS 리소스는 팀장 승인 뒤에만 바꾼다. **이 레포는 공개 레포다.**
5. 아래 "현재 상태"·"평가 핵심 숫자"는 수정 전 버전의 기록이다. 새 숫자는 `eval/rag/`에 쌓는다.

## 프로젝트 한 줄 (수정 전)

**역량다리(SkillBridge)**: 공고는 입사 문턱, 기업이 등록한 기준은 입사 후 실무 역량이다. 취준생은 지원 준비도(공고)와 실무 준비도(기업)로 진단받고, 지원 갭 → 실무 갭 순서의 학습경로를 추천받는다. Amazon Bedrock을 쓴다. KOSA×AWS AI 부트캠프 해커톤 06팀이고, **마감은 2026-11-22**.

- 채점: 문제해결력, 현장 적용성, 창의성, 전달력, AWS 활용도·팀워크 (각 20점). 항목별 목표와 진행 상황은 [docs/SCORECARD.md](docs/SCORECARD.md)에 있다.
- 명세: [docs/역량다리_구현명세.md](docs/역량다리_구현명세.md). 설계 결정과 이유: [DECISIONS.md](DECISIONS.md). 역할: [docs/TEAM.md](docs/TEAM.md).
- 시연 흐름(5분): [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)
- 문제 근거(공고 vs 실제 기술, 공개 사례 5건): [docs/EVIDENCE_POSTING_GAP.md](docs/EVIDENCE_POSTING_GAP.md). 기업 A·B·C는 가상, D는 공개 자료 재구성, **E~H는 멘토(김민관 대표)를 통한 현업 청취 기준**([docs/INTERVIEWS.md](docs/INTERVIEWS.md))

## 반드시 지킬 규칙

1. **키와 토큰은 `.env`에만 둔다.** 채팅, 로그, 커밋, 캡처에 값을 출력하지 않는다. 확인이 필요하면 이름과 길이만 본다. `.env`는 `.gitignore`에 있다.
2. **AWS 계정 955639821496**, 리전 `ap-northeast-2`, SSO 프로필 `kosa`에서 작업한다. 작업 전에 `sts get-caller-identity`로 계정을 확인한다.
3. **AWS 리소스를 만들거나 지우는 일은 팀장이 명시적으로 승인한 뒤에만 한다.** 만드는 리소스에는 모두 `project=kosa06` 태그를 단다.
4. **OpenSearch Serverless는 쓰지 않는다**(상시 과금). 벡터 저장소는 S3 Vectors를 쓴다. 유료 Marketplace 약정은 수락하지 않는다.
5. 교육 노트북 06에서 쓰는 팀 S3 버킷은 지우지 않는다.
6. **교육과정명을 지어내지 않는다.** 과정은 카탈로그(고용24 실데이터)에 있는 것만 낸다.
7. 이력서 원문은 저장하지 않는다. 기업에는 익명 집계만 준다. "채용 합불 판단에 쓰지 않음" 안내를 유지한다.
8. 점수는 규칙으로만 계산한다. LLM은 근거를 인용해 설명만 한다.
9. 평가셋(`eval/gold_*`)에 맞춰 스킬 사전을 튜닝하지 않는다(과적합).
10. Lambda에는 수집기용 API 키를 넣지 않는다.
11. 공개 배포에서는 원본 기업 설정을 바꾸지 않는다(ALLOW_BASE_WRITE=0). 방문자 수정은 샌드박스로만 간다.
12. 평가 숫자를 말할 때는 신뢰구간이 0을 포함하는지 확인한다. 유의하지 않은 개선을 확정된 것처럼 쓰지 않는다.

## 구조

| 경로 | 내용 |
|---|---|
| `backend/app/` | FastAPI. `pipeline/`(extract·normalize·implies·**bridge**·score·projectfit·recommend·diagnose·**family**·coach·market·simulate·supply·digital), `adapters/`(bedrock·athena·kb·storage[SQLite/DynamoDB]), `routers/`(market·diagnose·corp·coach), `guards/`(pii, limits: 샌드박스·IP/시간당 상한) |
| `frontend/src/` | React + Vite. 탭: 시장 분석(Market·Digital·SupplyMap·Quality), 취준생 진단, 기업 콘솔(Corp·Simulator) |
| `data/skills.csv` | 스킬 사전 171개 (한·영 별칭) |
| `seed/` | 기업 50곳: A~C 가상(목록에서 숨김) · D·I~Z24 공개 공고+기술 블로그 재구성(`research/public_companies/`의 batch_*.json → `build_companies.py`) · E~H 현업 청취. 예시 지원자 p1~p3(직군별 시연용) + t1~t3(테스트 전용), 기업 문서(`corp-docs/{A,B,C}`), 실데이터 공고(`market/postings_live.jsonl`, 잡알리오 11,637건), 고용24 과정 |
| `collectors/` | 고용24·잡알리오 수집기 (키 필요) |
| `eval/` | 정답셋, `run_eval.py`(`--model`·`--tag`로 모델 비교), 저장된 Bedrock 예측(`predictions/`, `predictions_haiku/`·`_sonnet/`), 결과(`report.md`·`results.json`), 라벨 규칙(`LABELING.md`), 설문(`SURVEY.md`), `sensitivity.py`(가중치 민감도), `bridge_eval.py`(연결되는 경험 오인정률), `gap/`(블로그 vs 공고 갭 측정) |
| `infra/` | `template.yaml`(CloudFormation: Lambda 함수 URL, Glue, Athena), `deploy.py`, `build_kb.py`(Bedrock KB + S3 Vectors) |

## 실행

```powershell
.\tasks.ps1 setup          # .venv, npm install, .env 생성 (.env.example 복사 → 값 채우기)
.\tasks.ps1 run            # API :8010 + 웹 :5173
.\tasks.ps1 test           # pytest 80개 통과가 기준 (GitHub Actions CI도 같은 것을 돌림)
.\tasks.ps1 eval           # AWS 없이, 저장된 예측으로 eval/report.md 재생성
```

- `BEDROCK_MOCK=1`이면 AWS 없이 규칙과 템플릿으로 돈다. `0`이면 Bedrock을 호출하고, 실패한 단계만 규칙으로 폴백한다.
- `DATA_MODE=live`이면 실데이터(공고·과정)를 쓴다.
- AWS 실호출 전에 `aws sso login --profile kosa`로 로그인한다. 윈도우에서 aws가 PATH에 없으면 `& "C:\Program Files\Amazon\AWSCLIV2\aws.exe"`로 실행한다.

## 현재 상태 (2026-11-16)

| 마일스톤 | 상태 |
|---|---|
| M0–M2 골격·규칙 엔진·Bedrock 파이프라인 | ✅ (Sonnet 4.6 추출, Haiku 4.5 정규화·설명, Titan v2 임베딩, Guardrail PII) |
| M3 실데이터 | ✅ 잡알리오 공고 11,637건, 고용24 과정 199개. S3·Glue·Athena 코드는 완료, 배포 전 |
| M4 기업 지식베이스 | ✅ KB 생성·적재 완료(2026-11-16). 코드(`adapters/kb.py`, tenant 필터 서버 강제, 다른 회사 결과 이중 차단, 테스트 포함). KB 생성(`infra/build_kb.py --yes`)은 아직 안 함 |
| M5 평가 | ✅ Bedrock 실측 + 95% 신뢰구간. 2차 라벨(κ)만 남음 |
| 공개 배포 가드 | ✅ 방문자 샌드박스(기업 설정 원본 보호), IP당 분당 8회, 시간당 Bedrock 상한 → 규칙 엔진, Lambda 동시 실행 3, DynamoDB 저장소 |
| 현업 청취 반영 | ✅ 기업 E~H(멘토 경유 실제 부서 기준), 상하위 스킬 보완(`pipeline/implies.py`), **프로젝트 적합도**(`pipeline/projectfit.py`). 경계값·도메인 단어는 멘토링에서 검증 필요 |
| 학습 코치 에이전트 | ✅ `pipeline/coach.py`: Converse 도구 선택 루프(도구 5개), tenant 고정, 과정 인용 검증, 규칙 플래너 폴백 |
| 진단 화면 (11-16) | ✅ 직군 3개(AI·ML·백엔드·데이터) → 회사 선택, 경력·시니어 기본 숨김. 결과 = ① 서류(공고) ② 실무(면접부터) ③ 할 일 순서(고용24·공식 문서 링크) ④ 내 프로젝트 + 같은 직군 회사, 코치는 오른쪽 고정. ①② 보조 정보는 커서 올리면 표시 |
| 목록에 없는 회사 (11-16) | ✅ 공고 붙여 넣기 → 서류는 공고로, 실무는 같은 직군 통계로 추정, Bedrock 예측은 참고(점수 미반영). `pipeline/family.py` |
| 연결되는 경험 (11-16) | ✅ 공고 단어로 안 쓴 이력서도 읽기: 비슷한 도구(보유일 때만) → 0.5, 개념 스킬만 Bedrock이 이력서 문장 인용해 연결 → 0.5. `pipeline/bridge.py`. 정답 '없음'에 잘못 준 비율 5.3%(구간 0~13%) |
| M6 배포 | ✅ 2026-11-16 배포(같은 날 재배포, DynamoDB 회사 50곳으로 갱신): https://fazwtcf7omav34gdiahcgvds3m0zyafv.lambda-url.ap-northeast-2.on.aws/ · DynamoDB · Athena 집계 확인(로컬과 일치) · KB `AQXJTFLOCI`(S3 Vectors, tenant 격리 검증) · 시연 키 없음(모두 Bedrock), IP당 분당 8 · 시간당 20 · 동시 2 |

평가 핵심 숫자 (`eval/report.md`). 발표에 쓰는 값이라 바뀌면 README·SCORECARD·DEMO_SCRIPT도 같이 고친다.

- 공고 추출 F1: 사전만 0.744 → LLM 추가 0.791 → 임베딩 추가 0.765(정밀도 하락) → LLM 재랭킹까지 0.809. **단, 30건으로는 95% 구간이 0을 포함 → 발표에서 핵심 근거로 쓰지 않는다**
- 이력서: 보유 역량을 갭으로 잘못 본 비율 23.4% → **7.4%** (감소폭 구간 +9.8~+22.5%p, 유의), 사전에 없는 표기 정확도 4.5% → 77.3%
- 가상 기업 시나리오에서 입사 후 실무 갭 커버율 **99.4%**(지원→실무 경로) vs 공고만 볼 때 51.3% (차이 구간 +42.7~+53.4%p, 유의). 과정 Hit@3 100%
- 무작위 표본 열(정답 1개)의 F1 0.000은 착시다. 이 열은 없는 스킬을 지어내는지 보는 용도다.
- **공고와 실무의 갭(핵심 근거)**: 같은 팀 블로그 원문을 Bedrock으로 뽑아 그 팀 공고와 비교 → 블로그 기술 68개 중 31개(**45.6%**, 구간 31.9~60.0%)가 공고에 없음, 10개 회사. `eval/gap/`. 예전 34%·25%·기술별 100%는 조사 지시가 편향돼 **쓰지 않는다**
- 모델 비교(`report_haiku.md`·`report_sonnet.md`): 공고 F1 Haiku 0.711 vs Sonnet 0.809(차이 구간 −0.012~+0.209, 유의 아님). 이력서 오탐률 둘 다 8.5%, Haiku가 1.7배 빠르고 비용 1/3
- 가중치 민감도(`sensitivity.py`): 필수 1.5~3이면 점수 평균 ±1.5점·회사 순위 상관 0.98, 할 일 순서 불변. 부분·검증 0.5가 가장 민감(±6점)
- 데이터 한계: 잡알리오는 **공공기관** 공고라 민간 IT 진단의 시장 근거로는 어색함. 민간 공고 API(사람인·로켓펀치) 승인 대기 중

## 다음 할 일

| 우선 | 일 | 담당 | 방법 |
|---|---|---|---|
| 1 | 2차 라벨 30건 → `eval/gold_postings_b.jsonl` 푸시 (`run_eval.py`가 κ를 자동 계산) | 김채희 | `eval/LABELING.md` 4절. **빈 시트 `gold_postings_b.todo.jsonl`에서 시작, 1차 라벨 파일은 열지 않기** |
| 2 | 슬라이드 8장 이내 + 리허설 2회. 메시지: 갭은 있다(45.6%) → 공개 자료로는 여기까지 → 기업이 표시해야 한다 | 변유민·이승연 | DEMO_SCRIPT.md, DECISIONS.md(예상 질문 근거) |
| 3 | 민간 공고 API 승인되면 수집기 연결(키는 `.env`의 `ROCKETPUNCH_API_KEY`·사람인, Lambda에 넣지 않음). 19일까지 안 되면 할 일 순서의 잡알리오 시장 적합도를 같은 직군 회사 통계로 교체 | 변유민 | — |
| 4 | 설문 5명 이상 + 시연 영상 `docs/demo.mp4` | 이승연 | `eval/SURVEY.md`, 배포 주소 |
| 5 | 시장 분석·기업 콘솔 탭을 핵심 메시지 중심으로 축소 | — | 멘토링 뒤 결정 |

배포: 코드를 바꾸면 `python infra/deploy.py --yes`. 회사 seed를 바꿨으면 DynamoDB 회사 항목도 갱신해야 한다(`init()`은 새 회사만 넣음). 스택 삭제는 해커톤 끝난 뒤 팀장 승인 후.

## 협업

- 레포: https://github.com/YuMinBee/skillbridge-kosa06 (비공개). 작업은 각자 브랜치에서 하고 PR로 합친다. 시작 전에는 `git pull`을 한다.
- 결정을 바꾸면 `DECISIONS.md`에 날짜와 이유를 적는다.
