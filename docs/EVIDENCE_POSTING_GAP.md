# 공고 vs 실제 기술: 공개 자료 사례 (2026-11-10 조사)

> 전제(2026-11-10 수정): 공고는 **입사 문턱**을 적고, 입사 후에는 **추가 기술**이 필요하다. 공고가 틀렸거나 숨긴다는 주장이 아니다.
> 질문: 채용 공고의 자격요건만 보면, 그 팀이 입사 후 실제로 쓰는 기술까지 드러나는가?
> 방법: 같은 회사(가능하면 같은 직무)의 공고와 기술 블로그·발표·보도자료를 비교했다. 인용은 원문을 직접 확인한 것만 적었다. ✔ 표시는 팀장 세션에서 한 번 더 열어 확인한 것이다.

## 요약

| # | 회사 · 직무 | 공고 자격요건에 없는 실제 기술 | 강도 |
|---|---|---|---|
| 1 | 토스증권 · ML Engineer (LLM) ✔ | 쿠버네티스, Argo CD, vLLM, SGLang, Grafana, Kibana, 사내 ML 플랫폼 | 중~강 |
| 2 | 당근 · ML Engineer (ML 인프라) | TPU, GCP, Vertex AI Pipelines, TFX (발표 제목 기준) | 중 |
| 3 | 쏘카 · AI Engineer | BigQuery, Airflow, S3, RDS (다른 그룹 글) | 약 |
| 4 | 한국가스공사(대구) · AI·정보기술(전산) | LLM, RAG, 온톨로지, AI 에이전트, LLMOps, 벡터DB (보도자료) | 중~약 |
| 5 | 토스뱅크 · ML Engineer (ML/LLM Ops) | **반대 사례**: 공고에 도구가 아주 자세히 적혀 있음 | — |

## 말할 수 있는 것 / 과장인 것

말할 수 있는 것
- 일부 기업·기관(토스증권, 당근, 가스공사)은 공고 자격요건에 실제로 쓰는 도구와 인프라를 적지 않는다. 그 정보는 기술 블로그, 밋업, 보도자료에 따로 흩어져 있다.
- 그래서 지원자가 팀의 실제 기술을 알려면 공고와 블로그·발표를 함께 봐야 한다. 공공기관 NCS 공고처럼 형식이 정해진 공고에서는 차이가 특히 크다.
- **역량다리와의 연결:** 공고(지원 기준)는 그대로 쓰고, 입사 후 쓰는 기술은 기업이 실무 기준으로 따로 등록한다. 기업 콘솔의 "기업 자료로 실무 역량 초안 만들기"가 흩어진 자료(블로그·온보딩·스택 문서)를 실무 기준으로 모으는 기능이다. 토스증권 사례로 말하면: 공고(LLM 운영 경험)는 문턱, 블로그의 쿠버네티스·Argo CD·vLLM은 입사 후 실무다.

과장인 것 (발표에서 쓰지 않는다)
- "공고는 실제 기술을 숨긴다", "대부분의 공고가 그렇다". 5건뿐이고 1건(토스뱅크)은 반대다. 당근은 공고 옆에 블로그를 직접 링크해 둔다. 숨긴다기보다 **공고는 도구가 아니라 문제 중심으로 쓰인다**가 정확하다.
- "블로그의 기술 = 그 팀이 요구하는 역량". 같은 팀인지 확인 안 된 사례가 많고(쏘카, 가스공사), 블로그는 특정 시점 기록이며, 공공기관 기술은 외주로 구축되기도 한다.

## 사례 상세

### 1. 토스증권 · ML Engineer (LLM) ✔
- 공고: https://toss.im/career/job-detail?job_id=7575603003 (AI Tribe 소속)
  - "분류, 추출, 요약, 번역 등 텍스트 기반 문제에 맞는 모델을 직접 학습해요."
  - 자격요건: "LLM 또는 NLP 모델을 직접 만들고 운영해 본 경험이 있는 분을 찾아요."
  - 쿠버네티스·Argo·vLLM·SGLang·Grafana·Kibana·Python·PyTorch 모두 **페이지에 없음** (✔ 확인)
- 블로그: https://toss.tech/article/tech_talk_talk_2 (2026-08-21, 김민규 · 토스증권 Machine Learning Engineer, 팀명 미기재)
  - "토스증권은 쿠버네티스, Argo CD 같은 여러 기술 스택 위에서 움직여요."
  - "vLLM이나 SGLang 같은 서빙 프레임워크가 제공하는 지표들이 있었어요."
  - "Grafana — 메트릭을 수집해 추이와 이상을 탐지" / "Kibana — 단건 로그를 확인"
  - "그래서 ML 플랫폼을 직접 구축했습니다."
- 공고에만 있는 것: 다국어(cross-lingual) 모델, 뉴스·공시 분류·태깅
- 주의: 블로그 작성자가 AI Tribe 소속인지는 확인 못 함

### 2. 당근 · Software Engineer, Machine Learning - ML 인프라
- 공고: https://careers.daangn.com/jobs/role/7498021003/
  - "사내 프롬프트 스튜디오와 에이전트 시스템을 지원하는 LLM 라우터를 개발하고 있어요"
  - 요건에 적힌 기술은 사실상 "파이썬을 주요 언어로 사용하고 있어요"뿐
- 공고 하단 '연관 콘텐츠'에 회사가 직접 링크한 발표·글 (제목만 확인, 본문 미확인)
  - "당근에서 값비싼 TPU를 효율적으로 활용하는 방법 | 2026 당근 빌더 밋업" https://www.youtube.com/watch?v=bK0vd8E8sC8
  - "ML Infrastructure with GCP | 2025 당근 GCP 밋업" https://www.youtube.com/watch?v=CfAUzt0zIFM
  - "서버리스 ML 훈련 인프라 구축하기: Vertex AI Pipelines & TFX" https://medium.com/daangn/gcp-vertex-ai-pipelines-%EC%82%AC%EC%9A%A9%EA%B8%B0-10b3387ba736
- 해석: 정보가 비공개인 게 아니라 **자격요건 칸에 없을 뿐**이다

### 3. 쏘카 · AI Engineer (Senior) — 약한 사례
- 공고(마감): https://career.rememberapp.co.kr/job/posting/279193
  - "Pytorch와 같은 트레이닝 프레임워크에 능숙하신 분" / 우대 "AWS 혹은 GCP등 클라우드 플랫폼 사용 경험" / "모델 경량화 및 Edge device 배포 경험"
- 블로그: https://tech.socar.kr/data/2024/03/12/ai-car-wash (2024-03-12, 데이터프로덕트그룹)
  - "BigQuery 에 주기적으로 적재 합니다" / "Airflow를 통해 관리 하고 있습니다"
- 주의: 블로그는 다른 그룹 글이다

### 4. 한국가스공사(본사 대구) · 일반직 6급 AI·정보기술(전산) — 대경권
- 공고: 2026년 하반기 신입 채용 (접수 2026-09-07~09-15) https://jasoseol.com/recruit/105932
  - 전공 범위: "소프트웨어 설계 및 개발, 데이터베이스 구축, 프로그래밍 언어 활용(Java, Python 포함), 정보시스템 구축 관리(네트워크 포함), IT 신기술 및 트렌드 등"
  - IT 자격증: "컴퓨터활용능력 1급, 정보처리기사"
  - NCS 직무기술서 원문은 미확인
- 기관의 실제 추진 (보도자료)
  - 한국경제 2026-07-22 https://www.hankyung.com/article/202607229779P : "인공지능(AI)과 온톨로지 기술을 활용해 분산된 업무 데이터를 통합·연결하는 'AX 플랫폼' 구축에 본격 착수"
  - 벤처스퀘어 2025-09-10 https://www.venturesquare.net/1003901 : "온프레미스 환경에서 대규모 언어모델(LLM)과 검색 증강 생성(RAG) 기술을 기반으로…"
- 주의: 기술 블로그가 아니라 언론 보도이고, 생성형 AI 시스템은 외부 업체가 구축한다. 차이가 외주 구조와 NCS 공고 형식 때문일 수 있다

### 5. 토스뱅크 · ML Engineer (ML/LLM Ops) — 반대 사례
- 공고: https://toss.im/career/job-detail?job_id=5498959003
  - "ScyllaDB 클러스터 기반의 Feature Store를 운영하고…", "Triton Inference Server, vLLM, SGLang 등…", "Terraform, Helm, ArgoCD 등…"
- 발표(SLASH24): https://toss.im/slash-24/sessions/11 , https://toss.im/slash-24/sessions/26 — 소개문에는 도구 이름이 없음
- 결론: 이 경우는 공고가 발표보다 구체적이다. 발표에 반대 사례로 함께 넣는다

## 확인하지 못한 것
당근 Medium·YouTube 본문, 토스증권 블로그 작성자의 소속 팀, 가스공사 NCS 직무기술서와 AX 담당 부서. 우아한형제들·카카오·iM뱅크·포스코DX는 공고 원문이나 같은 팀 글을 못 찾아 제외했다.
