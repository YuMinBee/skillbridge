# T2 RAG 검색 · 과제 추천 · 조합 실험 — 김승제

## 목표
NCS·과정 코퍼스를 검색해 **역량 연결(②)과 과제 추천(③)의 근거**를 댄다. 청크 토큰 길이 × 임베딩 모델 × 검색 방식 × 재랭킹 조합을 숫자로 비교해 고르고(발표 7번 슬라이드), 고른 조합을 Bedrock KB(S3 Vectors)에 올린다.

## 구현 목록 (순서대로)

| # | 파일 | 할 일 | 완료 기준 |
|---|---|---|---|
| 1 | `rag/chunk.py` | 고정 토큰(200/300/500/1000, 겹침 0·15%), 계층형(부모 1500·자식 300), 구조 단위(NCS 수행준거 한 줄 = 청크 하나). 토큰 수 계산 방법 기록 | 같은 문서 → 전략별 청크 목록 |
| 2 | `rag/embed_cache.py` | Bedrock 임베딩 1회 호출 후 `eval/trust/cache/` 저장(키: 모델·차원·청크 설정) | 두 번째 실행은 Bedrock 호출 0 |
| 3 | `rag/{bm25,hybrid,rerank}.py`, `rag/retrieve.py` | BM25(한글 2~3글자 n-gram), RRF 융합, 재랭킹(서울에 Bedrock Rerank 있으면 그것, 없으면 Haiku). `search()`는 [CONTRACTS 3절](CONTRACTS.md) | 코퍼스 없을 때는 기존 `seed/courses`로 동작 |
| 4 | `agents/retriever.py` | 직군 + 보유 스킬 → 해당 NCS 능력단위·수행준거 묶음(② 기준) | T1 supervisor가 부를 수 있음 |
| 5 | `agents/recommend_task.py` | 갭·STAR 빈칸 → NCS 수행준거 근거로 증명 과제 + 고용24 과정(카탈로그 대조). [CONTRACTS 4절](CONTRACTS.md) | 테스트: 카탈로그에 없는 과정 이름은 절대 안 나감 |
| 6 | `eval/trust/run_retrieval.py` | `gold_reco_dev`로 Recall@1/5/10, MRR@10, nDCG@10, p50/p95 지연, 1,000질의당 비용, 인덱스 크기, 95% 구간 | `results.json`의 `retrieval` 칸 채움 |
| 7 | 저장소 비교 | 로컬 정확 검색(기준) vs S3 Vectors(근사): 재현율 손실·지연·월 비용 | 표 1개 |
| 8 | `infra/build_kb.py` | 고른 조합으로 KB 재구축(실행은 팀장 승인 후) | 배포 환경에서 `search()`가 KB 사용 |

## 확인된 것 (2026-11-17, 계정 955639821496, 서울 리전 실제 호출)
| 모델 | 호출 ID | 차원 | 비고 |
|---|---|---|---|
| Titan Text Embeddings V2 | `amazon.titan-embed-text-v2:0` (온디맨드) | 256·512·1024 | 서울 안에서 처리. 이미 KB에 쓰는 중 |
| Cohere Embed v4 | `global.cohere.embed-v4:0` (교차 리전 프로필만, `apac.`은 안 됨) | 기본 1536 (요청 시 256·512·1024 가능한지 확인) | 서울 밖에서 처리될 수 있음 → 발표 시 언급 |
| 재랭킹(Rerank) | **서울 리전에 없음** | — | Haiku 재랭킹으로 대체하고, 그 이유를 표에 적는다 |

## 먼저 확인할 것 (추측으로 쓰지 말고 출처 링크를 `eval/trust/NOTES.md`에)
- 서울 리전(ap-northeast-2)에서 쓸 수 있는 임베딩·Rerank 모델 ID, 모델별 입력 토큰 상한·차원
- Bedrock KB 청크 전략 옵션, S3 Vectors 제약(메타데이터 크기 등)
- **토큰 길이 실험**: 청크가 모델 입력 상한을 넘으면 잘린다. "청크 길이 × 모델 상한 → Recall" 그래프 하나를 만든다

## 지킬 것
- `gold_*_test.jsonl`은 열지 않는다. 튜닝은 dev로만.
- OpenSearch Serverless 금지. 실험은 로컬, 배포만 S3 Vectors.

## Claude에게 줄 첫 지시
```
너는 T2 담당이다. AGENTS.md, docs/pivot/PLAN.md, docs/pivot/CONTRACTS.md, docs/pivot/T2_RAG.md를 읽어라.
브랜치 t2-rag에서 작업한다. CONTRACTS.md 7절의 T2 파일만 고친다. eval/trust/gold_*_test.jsonl은 절대 열지 마라.
코퍼스가 아직 없으면 seed/courses로 구현 목록 1→3(chunk → embed_cache → search) 골격을 먼저 돌리고 테스트를 붙여라.
```
