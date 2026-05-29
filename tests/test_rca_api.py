"""End-to-end test of the full self-healing loop through RCA.

ingest -> evaluate (incidents) -> analyze (root cause), via the API.
"""

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


def test_full_loop_failure_to_root_cause(client: TestClient) -> None:
    _ingest(client, "rca-loop-1", "spark_eventlog_failure.jsonl")
    client.post("/api/v1/observability/runs/rca-loop-1/evaluate")

    resp = client.post("/api/v1/remediation/runs/rca-loop-1/analyze")
    assert resp.status_code == 200, resp.text
    analysis = resp.json()

    assert analysis["run_id"] == "rca-loop-1"
    assert analysis["category"] == "memory_pressure"
    assert analysis["confidence"] >= 0.8
    assert len(analysis["recommended_actions"]) >= 1
    # incidents from the evaluate step are linked to the analysis.
    assert len(analysis["incident_ids"]) >= 1


def test_analysis_persisted_and_retrievable(client: TestClient) -> None:
    _ingest(client, "rca-loop-2", "spark_eventlog_failure.jsonl")
    client.post("/api/v1/observability/runs/rca-loop-2/evaluate")
    client.post("/api/v1/remediation/runs/rca-loop-2/analyze")

    got = client.get("/api/v1/remediation/runs/rca-loop-2/analysis")
    assert got.status_code == 200, got.text
    assert got.json()["category"] == "memory_pressure"


def test_analyze_is_idempotent(client: TestClient) -> None:
    _ingest(client, "rca-idem", "spark_eventlog_failure.jsonl")
    client.post("/api/v1/observability/runs/rca-idem/evaluate")

    first = client.post("/api/v1/remediation/runs/rca-idem/analyze").json()
    second = client.post("/api/v1/remediation/runs/rca-idem/analyze").json()
    assert first["analysis_id"] == second["analysis_id"]


def test_successful_run_has_no_meaningful_cause(client: TestClient) -> None:
    _ingest(client, "rca-ok", "spark_eventlog_success.jsonl")
    client.post("/api/v1/observability/runs/rca-ok/evaluate")

    resp = client.post("/api/v1/remediation/runs/rca-ok/analyze")
    assert resp.status_code == 200
    assert resp.json()["category"] == "unknown"
    assert resp.json()["confidence"] == 0.0


def test_analyze_unknown_run_returns_404(client: TestClient) -> None:
    resp = client.post("/api/v1/remediation/runs/missing/analyze")
    assert resp.status_code == 404


def test_get_analysis_before_analyze_returns_404(client: TestClient) -> None:
    _ingest(client, "rca-none", "spark_eventlog_success.jsonl")
    resp = client.get("/api/v1/remediation/runs/rca-none/analysis")
    assert resp.status_code == 404
