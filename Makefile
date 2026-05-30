.DEFAULT_GOAL := help
PY := uv run --python 3.12

.PHONY: help setup lint format typecheck test coverage check run-local up down build demo demo-list datasets seed-corpus

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install all dependencies (incl. dev + extras)
	uv sync --python 3.12 --all-extras

lint: ## Lint with ruff + black --check
	$(PY) ruff check src tests
	$(PY) black --check src tests

format: ## Auto-fix with ruff + black
	$(PY) ruff check --fix src tests
	$(PY) black src tests

typecheck: ## Type-check with mypy (strict)
	$(PY) --with mypy mypy src

test: ## Run unit tests
	$(PY) pytest -q

coverage: ## Run tests with coverage gating (matches CI)
	$(PY) pytest -q --cov --cov-report=term-missing --cov-fail-under=70

check: lint typecheck test ## Run the full local gate

run-local: ## Run the API with autoreload
	$(PY) uvicorn dataforge.main:app --reload --host 0.0.0.0 --port 8000

up: ## Start the local stack
	docker compose up --build

down: ## Stop the local stack
	docker compose down -v

build: ## Build the app image
	docker build -t dataforge:local .

demo: ## Drive the self-healing loop against a running API (BASE_URL=...)
	scripts/demo_self_heal.sh

demo-list: ## List available chaos scenarios
	$(PY) python -m dataforge.simulator --list

datasets: ## List shipped public-dataset loaders
	$(PY) python -m dataforge.datasets list

seed-corpus: ## Seed the running RAG corpus with all shipped datasets (BASE_URL=...)
	$(PY) python -m dataforge.datasets ingest --dataset postmortems --base-url $${BASE_URL:-http://localhost:8000}
	$(PY) python -m dataforge.datasets ingest --dataset loghub_spark --base-url $${BASE_URL:-http://localhost:8000}
