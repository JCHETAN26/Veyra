"""End-to-end tests for the orchestrated self-healing loop (coordinator).

A single call runs ingest -> detect -> explain -> recall -> propose, stopping
at the human approval gate.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _payload(run_id: str, fixture: str) -> dict[str, str]:
    return {
        "run_id": run_id,
        "content": (FIXTURES / fixture).read_text(),
    }


def test_failed_run_processes_to_needs_approval(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/orchestration/process/event-log",
        json=_payload("loop-fail", "spark_eventlog_failure.jsonl"),
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()

    assert report["run_id"] == "loop-fail"
    assert report["outcome"] == "needs_approval"
    assert report["run"]["status"] == "failed"
    assert len(report["incidents"]) >= 1
    assert report["analysis"]["category"] == "memory_pressure"
    # A workflow is proposed and parked at the approval gate.
    assert report["workflow"] is not None
    assert report["workflow"]["state"] == "pending_approval"


def test_healthy_run_processes_to_healthy(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/orchestration/process/event-log",
        json=_payload("loop-ok", "spark_eventlog_success.jsonl"),
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()

    assert report["outcome"] == "healthy"
    assert report["incidents"] == []
    assert report["analysis"] is None
    assert report["workflow"] is None


def test_loop_stops_at_approval_gate_then_human_approves(client: TestClient) -> None:
    # The coordinator never auto-approves; a human completes the loop.
    client.post(
        "/api/v1/orchestration/process/event-log",
        json=_payload("loop-approve", "spark_eventlog_failure.jsonl"),
    )

    # Still pending until a human acts.
    wf = client.get("/api/v1/orchestration/runs/loop-approve/remediation").json()
    assert wf["state"] == "pending_approval"

    # Human approves -> loop completes to resolved.
    resp = client.post(
        "/api/v1/orchestration/runs/loop-approve/remediation/approve",
        json={"approver": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "resolved"


def test_retrieval_context_shared_across_loop_runs(client: TestClient) -> None:
    # Process two similar OOM runs; the second should see the first as similar,
    # proving the coordinator shares the RAG index with the API path.
    client.post(
        "/api/v1/orchestration/process/event-log",
        json=_payload("loop-oom-a", "spark_eventlog_failure.jsonl"),
    )
    resp = client.post(
        "/api/v1/orchestration/process/event-log",
        json=_payload("loop-oom-b", "spark_eventlog_oom_other.jsonl"),
    )
    similar_ids = [s["run_id"] for s in resp.json()["similar_incidents"]]
    assert "loop-oom-a" in similar_ids

    # And the same index is visible through the RAG API.
    api = client.get("/api/v1/rag/runs/loop-oom-b/similar").json()
    assert "loop-oom-a" in [s["run_id"] for s in api["results"]]


def test_process_run_over_already_ingested(client: TestClient) -> None:
    # Ingest separately, then process the existing run.
    client.post(
        "/api/v1/ingestion/event-logs",
        json=_payload("loop-pre", "spark_eventlog_failure.jsonl"),
    )
    resp = client.post("/api/v1/orchestration/runs/loop-pre/process")
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "needs_approval"
