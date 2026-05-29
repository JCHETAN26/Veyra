"""End-to-end tests for the observability evaluation path via the API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _ingest(client: TestClient, run_id: str, fixture: str) -> None:
    content = (FIXTURES / fixture).read_text()
    resp = client.post(
        "/api/v1/ingestion/event-logs",
        json={"run_id": run_id, "content": content},
    )
    assert resp.status_code == 200, resp.text


def test_failed_run_raises_incidents(client: TestClient) -> None:
    _ingest(client, "obs-fail-1", "spark_eventlog_failure.jsonl")

    resp = client.post("/api/v1/observability/runs/obs-fail-1/evaluate")
    assert resp.status_code == 200, resp.text
    incidents = resp.json()
    types = {i["anomaly_type"] for i in incidents}

    # OOM failure run -> failure incident (critical) + excessive spill.
    assert "run_failure" in types
    assert "excessive_spill" in types
    failure = next(i for i in incidents if i["anomaly_type"] == "run_failure")
    assert failure["severity"] == 50  # CRITICAL


def test_successful_run_raises_no_incidents(client: TestClient) -> None:
    _ingest(client, "obs-ok-1", "spark_eventlog_success.jsonl")
    resp = client.post("/api/v1/observability/runs/obs-ok-1/evaluate")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_evaluation_is_idempotent(client: TestClient) -> None:
    _ingest(client, "obs-idem", "spark_eventlog_failure.jsonl")

    client.post("/api/v1/observability/runs/obs-idem/evaluate")
    client.post("/api/v1/observability/runs/obs-idem/evaluate")

    listed = client.get("/api/v1/observability/runs/obs-idem/incidents").json()
    keys = [i["incident_id"] for i in listed]
    assert len(keys) == len(set(keys))  # no duplicates


def test_open_incidents_listed(client: TestClient) -> None:
    _ingest(client, "obs-open", "spark_eventlog_failure.jsonl")
    client.post("/api/v1/observability/runs/obs-open/evaluate")

    resp = client.get("/api/v1/observability/incidents")
    assert resp.status_code == 200
    run_ids = {i["run_id"] for i in resp.json()}
    assert "obs-open" in run_ids


def test_evaluate_unknown_run_returns_404(client: TestClient) -> None:
    resp = client.post("/api/v1/observability/runs/nope/evaluate")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"
