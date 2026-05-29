# DataForge AI

AI-native operational intelligence platform for data pipelines. Detects
anomalies in Spark/Databricks pipelines, explains root causes, retrieves
similar past incidents, and proposes safe remediations behind a human
approval gate.

This repository is the **MVP modular monolith**: the seven platform domains
run as internal modules of a single FastAPI app sharing one Docker Compose
stack, with clean contract boundaries so each module can be split into its
own service later. See `build-plan.md` for the full vision.

## Architecture (MVP)

```
src/dataforge/
├── app.py            # composition root (app factory)
├── main.py           # uvicorn entrypoint
├── registry.py       # active module list
├── core/             # config, logging, observability, errors, middleware
├── contracts/        # shared, versioned Pydantic contracts
└── modules/          # the 7 domains, each implementing DomainModule
    ├── gateway/
    ├── ingestion/
    ├── metadata/
    ├── rag/
    ├── observability/
    ├── remediation/
    └── orchestration/
```

Each module exposes a router (mounted at `/api/v1/<name>`), lifecycle hooks,
and a health check. The app factory mounts them uniformly from `registry.py`.

## Tech stack

Python 3.12 · FastAPI · Pydantic v2 · structlog · OpenTelemetry · Prometheus.
Backing services (layered in as modules are implemented): PostgreSQL, Redis,
Qdrant, Redpanda, Temporal, Apache Spark + Delta Lake, MLflow.

## Quickstart

```bash
uv sync --all-extras          # install everything
# or, just the foundation:
uv sync

uv run uvicorn dataforge.main:app --reload
```

Then visit:
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health/live
- Readiness: http://localhost:8000/health/ready
- Metrics: http://localhost:8000/metrics

## Make targets

```bash
make setup            # uv sync + install dev deps
make lint             # ruff + black --check
make format           # ruff --fix + black
make typecheck        # mypy
make test             # pytest
make run-local        # uvicorn with reload
make up               # docker compose up
make down             # docker compose down
```

## Engineering rules (from build-plan.md)

- No direct pushes to `main`; every change is PR-driven and CI-gated.
- All code typed; all features tested; observability before deployment.
- Contracts-first: modules exchange data only via `contracts/`.
