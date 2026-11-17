# T4 화면 · 웹 Claude 캡처 · 블라인드 설문 · 시연 영상 — 이승연

## 목표
한 화면에서 **이력서 입력 → 진행 상태 → 강점(STAR) → 갭 → 추천 → 근거 원문 → 비용**이 보이고, 다른 화면에서 **웹 방식 vs 우리 방식 신뢰도 비교**가 보이게 한다. 발표 1번(웹 Claude 캡처)·5번(블라인드 선호) 자료도 이 트랙이 만든다.

## 구현 목록 (순서대로)

| # | 파일 | 할 일 | 완료 기준 |
|---|---|---|---|
| 1 | `frontend/src/tabs/Analyze.jsx`(새 기본 탭) | 이력서 + 직군 입력 → `POST /api/analyze` → job_id를 localStorage에 → 2초마다 `GET /api/jobs/{id}` | 탭을 닫았다 열어도 이어서 보임 |
| 2 | 진행 상태 | star → retriever → recommend → verifier → cost 단계가 하나씩 켜짐, 단계별 시간 | fixtures `job_running.json` |
| 3 | 강점 카드 | 경험마다 S·T·A·R 4칸, 채운 칸은 원문 인용, 빈 칸은 회색 + `missing_hint`. 수준(strong/ok/weak) | fixtures `job_done.json` |
| 4 | 갭·추천 | 추천마다 `[1]` 인용, 누르면 오른쪽 근거 패널(원문·NCS·과정 링크). `abstained`는 "근거가 없어 추천하지 않음"을 **기능처럼** 보이게 | fixtures `job_abstained.json` |
| 5 | 비용 줄 | 토큰·$·단계별 막대 | |
| 6 | `frontend/src/tabs/Trust.jsx` | `eval/trust/results.json`을 읽어 웹 vs 우리 비교, 구간 표시, 사람 A–B 일치도 나란히 | fixtures `results.json` |
| 7 | 기존 탭 정리 | 기업 콘솔·시뮬레이터·시장 분석 숨김(코드 유지) | |
| 8 | `docs/pivot/captures/` | 웹 Claude(claude.ai)에 시연 이력서 + "내 역량 분석하고 과제 추천해 줘" 3회 캡처. 일반론·지어낸 과정·회차마다 다른 답 표시 | 발표 1번 슬라이드 |
| 9 | `eval/SURVEY.md` | 블라인드 비교: 같은 이력서의 웹 결과 vs 우리 결과를 A/B로 가리고 "더 믿을 만한 쪽·이유". 5~10명 | 발표 5번 |
| 10 | `docs/demo.mp4` | 시연 영상 | |

## 백엔드 없이 시작하기
`docs/pivot/fixtures/`의 JSON으로 화면부터 만든다. fixtures의 숫자는 예시라 화면 개발에만 쓰고 발표에 쓰지 않는다.

## Claude에게 줄 첫 지시
```
너는 T4 담당이다. AGENTS.md, docs/pivot/PLAN.md, docs/pivot/CONTRACTS.md, docs/pivot/T4_FRONTEND.md를 읽어라.
브랜치 t4-frontend에서 작업한다. CONTRACTS.md 7절의 T4 파일만 고친다.
docs/pivot/fixtures의 JSON으로 Analyze 탭(구현 목록 1~5)을 먼저 만들어라. 백엔드 주소는 나중에 바꾼다.
```
