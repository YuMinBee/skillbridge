# 06팀 역할 분담 · AWS 서비스 선정 이유

> 평가 항목 "AWS 기술 활용도 및 팀워크(20점)" 근거 문서. 제출 마감 2026-11-22.
> 역할은 이전 팀 프로젝트(PinPoint)에서 각자 맡았던 영역을 기준으로 나눴습니다.

## 역할

| 팀원 | 담당 | 주요 산출물 | 이전 프로젝트에서 맡은 영역 |
|---|---|---|---|
| 변유민 (팀장) | 기획·발표, AWS 계정·Bedrock 접근, **Bedrock 에이전트 파이프라인** (구조화 추출 → 정규화 → 근거 인용 검증, Guardrail) | `backend/app/adapters/bedrock.py`, `pipeline/extract·normalize.py`, 시연 시나리오, 발표 자료 | AI 방어 전략: 근거 수집 → LLM 호출 → 검증 |
| 김승제 | **백엔드·규칙 엔진** (준비도 점수, 학습경로, 공고 기준선, 기업 콘솔 API), **기업 문서 KB** (S3 Vectors, 기업별 분리 검색) | `backend/app/pipeline/score·recommend·diagnose.py`, `routers/corp.py`, KB 구성 | 문서 분석 엔진, 사례 DB, 백엔드 저장 |
| 김채희 | **데이터** (고용24 훈련과정·공공기관 채용 수집, S3·Athena 집계, 스킬 사전 151개 검토), **평가 정답 라벨링** | `collectors/`, `data/skills.csv`, `eval/gold_*.jsonl`, 데이터 출처 표 | 사례 DB 구축, 수동 자료 수집 |
| 이승연 | **화면** (React 3개 탭: 시장 분석·취준생 진단·기업 콘솔), 시연 UX·데모 영상 | `frontend/`, 화면 캡처, 데모 영상 | 검토 화면, Streamlit·Next.js 화면 |

공동 작업
- 평가 정답 라벨링은 명세대로 두 사람이 따로 한 뒤 맞춰 봅니다 (김채희 + 김승제, 불일치는 팀장이 판정).
- 발표 리허설·질의응답 준비는 전원.

## AWS 서비스 선정 이유

| 서비스 | 쓰는 곳 | 왜 이것인가 | 대안과 안 쓴 이유 |
|---|---|---|---|
| Amazon Bedrock (Converse, 구조화 출력) | 공고·이력서 스킬 추출, 설명 생성 | 서울 리전, JSON 스키마 강제로 파싱 오류 감소 | Bedrock Agents: 단계가 고정이라 파이프라인이 더 투명하고 trace 표시가 쉬움 |
| Titan Text Embeddings V2 | 사전에 없는 표현 정규화, KB 검색 | 서울 리전 사용 가능, 한국어 지원 | — |
| Bedrock Knowledge Base + S3 Vectors | 기업 문서 근거 검색 (tenant 필터) | 상시 과금 없음 | OpenSearch Serverless: 최소 OCU 상시 과금 |
| Bedrock Guardrails | 이력서 PII 마스킹 | 한국어 PII 필터 | 직접 정규식만으로는 누락 위험 |
| S3 · EventBridge · Lambda | 공고 수집·추출 배치 | 서버리스, 원본 보존(raw/) | EC2 상시 서버: 비용·운영 부담 |
| Athena | 지역·직무·월별 스킬 언급률 집계 | S3 위에서 SQL, 쓴 만큼 과금 | RDS: 상시 과금 |
| Lambda + API Gateway (Mangum) | API 배포 | FastAPI 그대로 배포 | — |
| DynamoDB | 기업 설정·익명 집계 | 서버리스 키-값 | — |

모든 리소스에 `project=kosa06` 태그를 붙입니다.
