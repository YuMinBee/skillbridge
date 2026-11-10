# 작업 인수인계 (AI 코딩 도구용)

> Claude Code는 `CLAUDE.md`를, Codex는 이 파일을 자동으로 읽습니다. 사람이 읽어도 됩니다.
> 작업이 끝나면 아래 **현재 상태**와 **다음 할 일**을 갱신하고 커밋하세요. 마지막 갱신: 2026-11-10 (변유민 + Claude).

## 프로젝트 한 줄

**역량다리(SkillBridge)**: 공고는 입사 문턱, 기업이 등록한 기준은 입사 후 실무 역량이다. 취준생은 지원 준비도(공고)와 실무 준비도(기업)로 진단받고, 지원 갭 → 실무 갭 순서의 학습경로를 추천받는다. Amazon Bedrock을 쓴다. KOSA×AWS AI 부트캠프 해커톤 06팀이고, **마감은 2026-11-22**.

- 채점: 문제해결력, 현장 적용성, 창의성, 전달력, AWS 활용도·팀워크 (각 20점). 항목별 목표와 진행 상황은 [docs/SCORECARD.md](docs/SCORECARD.md)에 있다.
- 명세: [docs/역량다리_구현명세.md](docs/역량다리_구현명세.md). 설계 결정과 이유: [DECISIONS.md](DECISIONS.md). 역할: [docs/TEAM.md](docs/TEAM.md).
- 시연 흐름(5분): [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)
- 문제 근거(공고 vs 실제 기술, 공개 사례 5건): [docs/EVIDENCE_POSTING_GAP.md](docs/EVIDENCE_POSTING_GAP.md). 기업 A·B·C는 가상이고, 실제 기업 기준은 멘토(김민관 대표)께 요청 중

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
| `backend/app/` | FastAPI. `pipeline/`(extract·normalize·score·recommend·diagnose·coach·market·simulate·supply·digital), `adapters/`(bedrock·athena·kb·storage[SQLite/DynamoDB]), `routers/`(market·diagnose·corp·coach), `guards/`(pii, limits: 샌드박스·IP/시간당 상한) |
| `frontend/src/` | React + Vite. 탭: 시장 분석(Market·Digital·SupplyMap·Quality), 취준생 진단, 기업 콘솔(Corp·Simulator) |
| `data/skills.csv` | 스킬 사전 161개 (한·영 별칭) |
| `seed/` | 가상 기업 A·B·C, 예시 지원자, 기업 문서(`corp-docs/{A,B,C}`), 실데이터 공고(`market/postings_live.jsonl`, 잡알리오 11,637건), 고용24 과정 |
| `collectors/` | 고용24·잡알리오 수집기 (키 필요) |
| `eval/` | 정답셋, `run_eval.py`, 저장된 Bedrock 예측(`predictions/`), 결과(`report.md`·`results.json`), 라벨 규칙(`LABELING.md`), 설문(`SURVEY.md`) |
| `infra/` | `template.yaml`(CloudFormation: Lambda 함수 URL, Glue, Athena), `deploy.py`, `build_kb.py`(Bedrock KB + S3 Vectors) |

## 실행

```powershell
.\tasks.ps1 setup          # .venv, npm install, .env 생성 (.env.example 복사 → 값 채우기)
.\tasks.ps1 run            # API :8010 + 웹 :5173
.\tasks.ps1 test           # pytest 67개 통과가 기준 (GitHub Actions CI도 같은 것을 돌림)
.\tasks.ps1 eval           # AWS 없이, 저장된 예측으로 eval/report.md 재생성
```

- `BEDROCK_MOCK=1`이면 AWS 없이 규칙과 템플릿으로 돈다. `0`이면 Bedrock을 호출하고, 실패한 단계만 규칙으로 폴백한다.
- `DATA_MODE=live`이면 실데이터(공고·과정)를 쓴다.
- AWS 실호출 전에 `aws sso login --profile kosa`로 로그인한다. 윈도우에서 aws가 PATH에 없으면 `& "C:\Program Files\Amazon\AWSCLIV2\aws.exe"`로 실행한다.

## 현재 상태 (2026-11-10)

| 마일스톤 | 상태 |
|---|---|
| M0–M2 골격·규칙 엔진·Bedrock 파이프라인 | ✅ (Sonnet 4.6 추출, Haiku 4.5 정규화·설명, Titan v2 임베딩, Guardrail PII) |
| M3 실데이터 | ✅ 잡알리오 공고 11,637건, 고용24 과정 199개. S3·Glue·Athena 코드는 완료, 배포 전 |
| M4 기업 지식베이스 | 🟡 코드 완료(`adapters/kb.py`, tenant 필터 서버 강제, 다른 회사 결과 이중 차단, 테스트 포함). KB 생성(`infra/build_kb.py --yes`)은 아직 안 함 |
| M5 평가 | ✅ Bedrock 실측 + 95% 신뢰구간. 2차 라벨(κ)만 남음 |
| 공개 배포 가드 | ✅ 방문자 샌드박스(기업 설정 원본 보호), IP당 분당 8회, 시간당 Bedrock 상한 → 규칙 엔진, Lambda 동시 실행 3, DynamoDB 저장소 |
| 학습 코치 에이전트 | ✅ `pipeline/coach.py`: Converse 도구 선택 루프(도구 5개), tenant 고정, 과정 인용 검증, 규칙 플래너 폴백 |
| M6 배포 | 🟡 `infra/deploy.py` 완료(로컬 빌드 11.5MB 확인). **실제 배포는 팀장 승인 대기** |

평가 핵심 숫자 (`eval/report.md`). 발표에 쓰는 값이라 바뀌면 README·SCORECARD·DEMO_SCRIPT도 같이 고친다.

- 공고 추출 F1: 사전만 0.744 → LLM 추가 0.791 → 임베딩 추가 0.765(정밀도 하락) → LLM 재랭킹까지 0.809. **단, 30건으로는 95% 구간이 0을 포함 → 발표에서 핵심 근거로 쓰지 않는다**
- 이력서: 보유 역량을 갭으로 잘못 본 비율 23.4% → **7.4%** (감소폭 구간 +9.8~+22.5%p, 유의), 사전에 없는 표기 정확도 4.5% → 77.3%
- 가상 기업 시나리오에서 입사 후 실무 갭 커버율 **99.4%**(지원→실무 경로) vs 공고만 볼 때 51.3% (차이 구간 +42.7~+53.4%p, 유의). 과정 Hit@3 100%
- 무작위 표본 열(정답 1개)의 F1 0.000은 착시다. 이 열은 없는 스킬을 지어내는지 보는 용도다.

## 다음 할 일

| 우선 | 일 | 담당 | 방법 |
|---|---|---|---|
| 1 | 배포: `python infra/deploy.py --yes` → `python infra/build_kb.py --yes` → 출력된 `KB_ID`를 `.env`에 넣기 → 다시 배포 → 배포 주소에서 시장 탭 "집계: Athena" 확인 | 변유민 | **승인 후에만**. 함수 URL은 공개 주소라 Bedrock 비용이 나갈 수 있다 |
| 2 | 2차 라벨 30건 → `eval/gold_postings_b.jsonl` 푸시 (`run_eval.py`가 κ를 자동 계산) | 김채희 | `eval/LABELING.md` 4절 |
| 3 | 슬라이드 8장 이내 + 리허설 2회 | 변유민·이승연 | DEMO_SCRIPT.md |
| 4 | 설문 5명 이상 + 시연 영상 `docs/demo.mp4` | 이승연 | `eval/SURVEY.md`, 배포 주소 |
| 5 | (선택) 현업 인터뷰 한 줄, RELATED_WORK.md → 차별점 슬라이드 1장 | — | SCORECARD 2·3절 |

## 협업

- 레포: https://github.com/YuMinBee/skillbridge-kosa06 (비공개). 작업은 각자 브랜치에서 하고 PR로 합친다. 시작 전에는 `git pull`을 한다.
- 결정을 바꾸면 `DECISIONS.md`에 날짜와 이유를 적는다.
