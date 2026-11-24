# Bedrock Knowledge Base vs 직접 구현 (교육과정 검색)

질의응답 대비 실험. 서비스에는 쓰지 않는다. 실험 리소스(`kosa06-kbexp-*`)는 끝난 뒤 지웠다.

## 조건

- 질의 40개(이름 25 · 필요 15), 정답 = `run_retrieval.py`와 같은 Sonnet 판정 0/1/2. 판정 캐시는 `judge_retrieval.json`을 복사해 쓰고, KB 결과 중 새로 나온 쌍만 추가 판정(5건).
- 문서 = 고용24 과정 1,856개의 과정명 한 줄(직접 구현과 같은 텍스트), 청킹 없음, 저장소 S3 Vectors, 서울 리전.
- 정답 풀이 원래 7개 조합 + KB 결과라, `report_retrieval.md`와 소수점 셋째 자리가 조금 다를 수 있다.

## 결과 1 · 같은 Titan v2 1024 (2026-11-22, `results_kb_titan.json`)

| 방식 | nDCG@5 [95% 구간] | 이름 질의 | 필요 질의 | Recall@5 | KB − 이 방식 |
|---|---|---|---|---|---|
| 키워드(BM25) | 0.648 [0.53, 0.76] | 0.762 | 0.459 | 0.705 | +0.066 [−0.05, 0.17] 유의 아님 |
| 직접 구현 Titan 1024 | 0.716 [0.62, 0.81] | 0.797 | 0.581 | 0.840 | −0.001 [−0.00, 0.00] |
| **KB Titan 1024** | **0.715 [0.62, 0.81]** | 0.795 | 0.581 | 0.840 | — |
| 직접 구현 Cohere v4 (서비스) | 0.824 [0.74, 0.90] | 0.940 | 0.632 | 0.895 | −0.110 [−0.22, −0.01] 유의 |

- 상위 5개 겹침(KB vs 직접 Titan) 94%, KB 검색 지연 중앙값 약 0.33초.
- 같은 임베딩이면 KB와 직접 구현은 사실상 같다 → 옮기기는 어렵지 않다.

## 결과 2 · KB + Cohere Embed v4 (2026-11-24, `results_kb_cohere.json`)

- KB 생성 단계에서 거부: `Knowledge Base type does not support cohere.embed-v4:0 embedding model`.
- 서울 리전에서 Cohere v4는 `global.` 교차 리전 추론 프로필로만 열려 있다.
- 그래서 서비스에서 가장 좋았던 Cohere v4(0.824)를 쓰려면 지금처럼 직접 구현해야 한다. 확인한 것은 Cohere **v4**뿐이다.

## 다시 돌리기

AWS 리소스를 만들므로 팀장 승인 뒤에만: `python eval/trust/kb/kb_titan.py build` → `eval` → `python eval/trust/kb/cleanup.py`. 중간 파일은 `eval/trust/kb/out/`(git 제외).
