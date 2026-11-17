# T2 검색(RAG) 실험 — 김승제

## 목표
청크 크기 × 임베딩 모델 × 검색 방식 × 재랭킹 조합을 **숫자로 비교**해서 최선 조합을 고르고, 그 조합을 Bedrock KB(S3 Vectors)에 올린다. 발표에서 "이 조합을 고른 이유"를 표 하나로 말할 수 있어야 한다.

## 만들 것
1. `backend/app/rag/chunk.py`: 고정 토큰(200/300/500/1000, 겹침 0·15%), 계층형(부모 1500·자식 300), 구조 단위(NCS 수행준거 한 줄). 토큰 수는 실제 토크나이저 또는 근사(한글 1자 ≈ 1토큰 이하). 어떤 근사를 썼는지 기록한다.
2. `backend/app/rag/embed_cache.py`: Bedrock 임베딩을 한 번만 호출하고 `eval/rag/cache/`(gitignore)에 저장. 모델·차원·청크 설정이 키.
3. `backend/app/rag/{bm25,hybrid,rerank}.py`: BM25(한국어는 형태소 대신 2~3글자 n-gram으로 시작), RRF 융합, 재랭킹(Bedrock Rerank가 서울에 있으면 그것, 없으면 Haiku).
4. `backend/app/rag/retrieve.py`: [CONTRACTS 2절](../pivot/CONTRACTS.md)의 `search()`. `config="best"`를 확정 조합으로.
5. `eval/rag/run_retrieval.py`: `gold_dev.jsonl`로 Recall@1/5/10, MRR@10, nDCG@10, p50/p95 지연, 1,000질의당 비용, 인덱스 크기. 95% 부트스트랩 구간. `--split test`는 마지막에 한 번만.
6. 저장소 비교: 로컬 정확 검색(기준) vs S3 Vectors(근사)의 재현율 차이·지연·월 비용.
7. `infra/build_kb.py`: 고른 조합(청크 전략·임베딩 모델)으로 KB 재구축. 실행은 팀장 승인 후.

## 먼저 확인할 것 (추측으로 쓰지 말 것)
- 서울 리전(ap-northeast-2)에서 쓸 수 있는 임베딩·Rerank 모델 ID
- 모델별 입력 토큰 상한과 차원. Bedrock KB 청크 전략 옵션과 S3 Vectors 제약(메타데이터 크기 등)
- 출처 문서 링크를 `eval/rag/NOTES.md`에 적는다

## 지킬 것
- `gold_test.jsonl`은 열지 않는다. 튜닝은 dev로만 한다.
- OpenSearch Serverless 금지. 실험은 로컬, 배포만 S3 Vectors.

## Claude에게 줄 첫 지시
```
너는 T2 담당이다. AGENTS.md, docs/pivot/PLAN.md, docs/pivot/CONTRACTS.md, docs/pivot/T2_RAG.md를 읽어라.
브랜치 t2-rag에서 작업한다. CONTRACTS.md 6절의 T2 파일만 고친다. eval/rag/gold_test.jsonl은 절대 열지 마라.
코퍼스가 아직 없으면 seed/courses와 seed/market/postings_live.jsonl 일부로 chunk → embed_cache → search 골격을 먼저 돌려라.
```
