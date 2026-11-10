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
| Amazon Bedrock Converse (구조화 출력) · Sonnet 4.6 | 공고·이력서 스킬 추출 | 서울 리전, 도구 스키마 강제로 JSON 파싱 오류 없음 | 프롬프트 JSON: 형식 깨짐 위험 |
| Bedrock Converse (도구 선택) · Haiku 4.5 | 정규화 후보 선택, 설명 생성, **학습 코치 에이전트**(도구 5개 중 골라 호출) | 빠르고 저렴, 근거 밖 수식어가 적음 | Bedrock Agents 관리형: 진단은 단계를 고정해 trace·폴백을 투명하게, 자유 질문만 에이전트 루프로 |
| Titan Text Embeddings V2 | 사전에 없는 표현 정규화, KB 임베딩 | 서울 리전, 한국어 지원 | — |
| Bedrock Knowledge Base + S3 Vectors | 기업 문서 근거 검색 (tenantId 필터 서버 강제) | 상시 과금 없음 | OpenSearch Serverless: 최소 OCU 상시 과금 |
| Bedrock Guardrails | 이력서 PII 익명화 | 한국어 PII 필터 + 정규식 이중 | 정규식만으로는 누락 위험 |
| Lambda + 함수 URL (Mangum) | 프런트 + API 한 주소 | FastAPI 그대로, 동시 실행 상한으로 비용 상한 | API Gateway: 시연 규모에 불필요한 구성 요소 |
| DynamoDB (온디맨드, TTL) | 기업 설정, 방문자 샌드박스(24시간 TTL), 익명 진단 기록 | 콜드스타트에도 상태 유지, 쓴 만큼 과금 | Lambda /tmp SQLite: 인스턴스마다 상태가 달라짐 (로컬 개발용으로만 유지) |
| S3 raw/ · curated/ + Glue + Athena | 공고 원본 보존, 지역·직무별 스킬 언급률 SQL 집계 | S3 위에서 SQL, 쿼리당 1GB 상한 | RDS: 상시 과금 |
| CloudFormation | 위 리소스 전부 한 스택 (`infra/template.yaml`) | 한 명령으로 생성·삭제, 태그 일괄 | 콘솔 수작업: 재현 불가 |

수집(고용24·잡알리오)은 키가 필요한 일회성 배치라 로컬에서 돌리고 결과만 S3 raw/에 올립니다 (Lambda에 수집 키를 두지 않기 위해). 모든 리소스에 `project=kosa06` 태그를 붙입니다.
