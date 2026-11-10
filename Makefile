# Mac/Linux용. Windows는 tasks.ps1 사용 (.\tasks.ps1 run)
PY := .venv/bin/python

.PHONY: setup seed collect run api web test eval deploy

setup:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.txt
	cd frontend && npm install
	@test -f .env || cp .env.example .env

seed:
	$(PY) scripts/gen_market_sample.py
	$(PY) scripts/gen_fake_sessions.py

collect:  ## 고용24 훈련과정 + 잡알리오 공고 수집 (.env의 WORK24_KEY_TRAINING, ALIO_API_KEY 필요)
	$(PY) collectors/work24_courses.py
	$(PY) collectors/work24_courses.py --region-scan
	$(PY) collectors/alio_postings.py
	$(PY) collectors/build_supply.py

api:
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8010

web:
	cd frontend && npm run dev

run:
	$(MAKE) -j2 api web

test:
	$(PY) -m pytest backend/tests -q

eval:  ## 정답셋으로 지표 계산 → eval/report.md (저장된 Bedrock 예측 사용. 새로 돌리려면 make eval-live)
	$(PY) eval/run_eval.py

eval-live:  ## aws sso login --profile kosa 후
	$(PY) eval/run_eval.py --live

deploy:
	@echo "M6에서 구현 예정 (infra/)"
