"""End-to-end tests for the full self-healing loop through remediation.

ingest -> evaluate -> analyze -> propose -> approve/reject -> resolve/rollback.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _prepare(client: TestClient, run_id: str, fixture: str) -> None:
    """Ingest, evaluate, and analyze so the run has an RCA to propose from."""
    content = (FIXTURES / fixture).read_text()
    assert (
        client.post(
            "/api/v1/ingestion/event-logs",
            json={"run_id": run_id, "content": content},
        ).status_code
        == 200
    )
    client.post(f"/api/v1/observability/runs/{run_id}/evaluate")
    client.post(f"/api/v1/remediation/runs/{run_id}/analyze")


def test_full_loop_approve_resolves(client: TestClient) -> None:
    _prepare(client, "wf-1", "spark_eventlog_failure.jsonl")

    # Propose
    resp = client.post("/api/v1/orchestration/runs/wf-1/remediation")
    assert resp.status_code == 200, resp.text
    wf = resp.json()
    assert wf["state"] == "pending_approval"
    assert wf["proposal"]["cause_category"] == "memory_pressure"
    assert len(wf["proposal"]["actions"]) >= 1

    # Approve -> executes fallback chain -> resolves
    resp = client.post(
        "/api/v1/orchestration/runs/wf-1/remediation/approve",
        json={"approver": "alice"},
    )
    assert resp.status_code == 200, resp.text
    wf = resp.json()
    assert wf["state"] == "resolved"
    assert wf["approver"] == "alice"
    assert wf["applied_action_index"] is not None

    # The run's incidents are now resolved.
    incidents = client.get("/api/v1/observability/runs/wf-1/incidents").json()
    assert all(i["status"] == "resolved" for i in incidents)


def test_reject_path(client: TestClient) -> None:
    _prepare(client, "wf-2", "spark_eventlog_failure.jsonl")
    client.post("/api/v1/orchestration/runs/wf-2/remediation")

    resp = client.post(
        "/api/v1/orchestration/runs/wf-2/remediation/reject",
        json={"reason": "will handle manually"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "rejected"

    # Cannot approve a rejected (terminal) workflow.
    resp = client.post(
        "/api/v1/orchestration/runs/wf-2/remediation/approve",
        json={"approver": "bob"},
    )
    assert resp.status_code == 409


def test_propose_is_idempotent(client: TestClient) -> None:
    _prepare(client, "wf-3", "spark_eventlog_failure.jsonl")
    first = client.post("/api/v1/orchestration/runs/wf-3/remediation").json()
    second = client.post("/api/v1/orchestration/runs/wf-3/remediation").json()
    assert first["workflow_id"] == second["workflow_id"]
    assert first["state"] == second["state"]


def test_propose_without_analysis_conflicts(client: TestClient) -> None:
    # Ingest + evaluate but skip analyze -> no RCA to propose from.
    content = (FIXTURES / "spark_eventlog_failure.jsonl").read_text()
    client.post(
        "/api/v1/ingestion/event-logs",
        json={"run_id": "wf-4", "content": content},
    )
    client.post("/api/v1/observability/runs/wf-4/evaluate")

    resp = client.post("/api/v1/orchestration/runs/wf-4/remediation")
    assert resp.status_code == 409


def test_propose_unknown_run_404(client: TestClient) -> None:
    resp = client.post("/api/v1/orchestration/runs/missing/remediation")
    assert resp.status_code == 404


def test_audit_trail_recorded(client: TestClient) -> None:
    _prepare(client, "wf-5", "spark_eventlog_failure.jsonl")
    client.post("/api/v1/orchestration/runs/wf-5/remediation")
    client.post(
        "/api/v1/orchestration/runs/wf-5/remediation/approve",
        json={"approver": "carol"},
    )
    wf = client.get("/api/v1/orchestration/runs/wf-5/remediation").json()
    states = [t["to_state"] for t in wf["transitions"]]
    assert states == ["approved", "applying", "rerunning", "resolved"]
