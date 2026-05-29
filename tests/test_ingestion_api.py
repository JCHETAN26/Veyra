"""End-to-end tests for the ingestion -> metadata path via the API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _failure_log() -> str:
    return (FIXTURES / "spark_eventlog_failure.jsonl").read_text()


def test_ingest_then_read_back(client: TestClient) -> None:
    content = _failure_log()
    resp = client.post(
        "/api/v1/ingestion/event-logs",
        json={"run_id": "e2e-run-1", "content": content},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == "e2e-run-1"
    assert body["status"] == "failed"
    assert body["failure"]["error_class"] == "java.lang.OutOfMemoryError"

    # Read it back through the metadata module.
    got = client.get("/api/v1/metadata/runs/e2e-run-1")
    assert got.status_code == 200, got.text
    assert got.json()["run_id"] == "e2e-run-1"
    assert got.json()["metrics"]["num_failed_tasks"] == 1


def test_ingest_is_idempotent(client: TestClient) -> None:
    content = _failure_log()
    payload = {"run_id": "e2e-idem", "content": content}

    client.post("/api/v1/ingestion/event-logs", json=payload)
    client.post("/api/v1/ingestion/event-logs", json=payload)

    runs = client.get("/api/v1/metadata/runs?limit=500").json()
    matching = [r for r in runs if r["run_id"] == "e2e-idem"]
    assert len(matching) == 1


def test_get_unknown_run_returns_404(client: TestClient) -> None:
    resp = client.get("/api/v1/metadata/runs/does-not-exist")
    assert resp.status_code == 404


def test_readiness_reports_postgres_dependency(client: TestClient) -> None:
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()["dependencies"]}
    assert "postgres" in names
