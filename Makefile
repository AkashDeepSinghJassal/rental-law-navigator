# Rental Housing Law Navigator. Not legal advice.
PY = .venv/bin/python

setup:            ## install dependencies (needs uv: https://docs.astral.sh/uv/)
	uv sync

test:             ## unit + live tests (real DB, real LLMs, real Census Geocoder)
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

build-kb:         ## ingest -> extract -> consolidate (uses LLM_PROVIDER / LLM_MODEL from .env)
	$(PY) -m navigator ingest && $(PY) -m navigator extract && $(PY) -m navigator consolidate

outputs:          ## geocode, export rules/lookups/changes, self-check
	$(PY) -m navigator geocode && $(PY) -m navigator export && $(PY) -m navigator selfcheck

offline:          ## replay everything from the database cache with zero network calls
	NAVIGATOR_OFFLINE=1 $(PY) -m navigator run-all

frontend:         ## build the React front end into web/dist
	cd frontend && npm install && npm run build

serve:            ## web app on http://127.0.0.1:8765
	$(PY) -m navigator serve --port 8765

.PHONY: setup test lint build-kb outputs offline frontend serve
