.DEFAULT_GOAL := help
PY := uv run --python 3.12

.PHONY: help setup lint format typecheck test check run-local up down build

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

check: lint typecheck test ## Run the full local gate

run-local: ## Run the API with autoreload
	$(PY) uvicorn dataforge.main:app --reload --host 0.0.0.0 --port 8000

up: ## Start the local stack
	docker compose up --build

down: ## Stop the local stack
	docker compose down -v

build: ## Build the app image
	docker build -t dataforge:local .
