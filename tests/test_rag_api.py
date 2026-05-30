"""End-to-end tests for operational RAG retrieval via the API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _prepare(client: TestClient, run_id: str, fixture: str) -> None:
    """Ingest, evaluate, and analyze a run so it has a full failure profile."""
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


def test_similar_oom_runs_are_retrieved(client: TestClient) -> None:
    # Two distinct OOM failures from different apps, plus a clean run.
    _prepare(client, "rag-oom-1", "spark_eventlog_failure.jsonl")
    _prepare(client, "rag-oom-2", "spark_eventlog_oom_other.jsonl")
    _prepare(client, "rag-ok-1", "spark_eventlog_success.jsonl")

    for rid in ("rag-oom-1", "rag-oom-2", "rag-ok-1"):
        assert client.post(f"/api/v1/rag/runs/{rid}/index").status_code == 200

    resp = client.get("/api/v1/rag/runs/rag-oom-1/similar")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query_run_id"] == "rag-oom-1"

    result_ids = [r["run_id"] for r in body["results"]]
    # The other OOM run should be the top match; query run excluded from its own.
    assert "rag-oom-1" not in result_ids
    assert "rag-oom-2" in result_ids
    top = body["results"][0]
    assert top["run_id"] == "rag-oom-2"
    assert top["category"] == "memory_pressure"
    assert top["score"] > 0.5


def test_clean_run_does_not_match_oom(client: TestClient) -> None:
    _prepare(client, "rag-oom-3", "spark_eventlog_failure.jsonl")
    _prepare(client, "rag-ok-2", "spark_eventlog_success.jsonl")
    client.post("/api/v1/rag/runs/rag-oom-3/index")
    client.post("/api/v1/rag/runs/rag-ok-2/index")

    # With a strict threshold the clean run finds no operationally similar peer.
    resp = client.get("/api/v1/rag/runs/rag-ok-2/similar?min_score=0.5")
    ids = [r["run_id"] for r in resp.json()["results"]]
    assert "rag-oom-3" not in ids


def test_similar_unknown_run_returns_404(client: TestClient) -> None:
    resp = client.get("/api/v1/rag/runs/nope/similar")
    assert resp.status_code == 404


def test_index_returns_immediate_matches(client: TestClient) -> None:
    _prepare(client, "rag-a", "spark_eventlog_failure.jsonl")
    _prepare(client, "rag-b", "spark_eventlog_oom_other.jsonl")
    client.post("/api/v1/rag/runs/rag-a/index")

    resp = client.post("/api/v1/rag/runs/rag-b/index")
    assert resp.status_code == 200
    assert resp.json()["query_run_id"] == "rag-b"
