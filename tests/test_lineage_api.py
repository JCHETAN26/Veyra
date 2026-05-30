"""End-to-end tests for lineage registration, queries, and blast radius in
the coordinator report.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _register(client: TestClient, job: str, inputs, outputs, run_id=None) -> None:
    body = {"job_name": job, "inputs": inputs, "outputs": outputs}
    if run_id is not None:
        body["run_id"] = run_id
    resp = client.post("/api/v1/metadata/lineage", json=body)
    assert resp.status_code == 200, resp.text


def test_register_and_query_neighbors(client: TestClient) -> None:
    _register(client, "etl", ["raw_orders"], ["clean_orders"])
    resp = client.get("/api/v1/metadata/lineage/raw_orders/neighbors?direction=downstream")
    assert resp.status_code == 200
    assert [n["name"] for n in resp.json()["neighbors"]] == ["clean_orders"]


def test_blast_radius_endpoint(client: TestClient) -> None:
    _register(client, "j1", ["raw"], ["clean"])
    _register(client, "j2", ["clean"], ["agg"])
    _register(client, "j3", ["agg"], ["dash"])

    resp = client.get("/api/v1/metadata/lineage/raw/blast-radius")
    assert resp.status_code == 200
    body = resp.json()
    impacted = {i["name"]: i["depth"] for i in body["impacted"]}
    assert impacted == {"clean": 1, "agg": 2, "dash": 3}


def test_failed_run_report_includes_blast_radius(client: TestClient) -> None:
    # Register lineage tying a failing run's output into a downstream chain.
    _register(
        client,
        "orders_etl",
        ["raw_orders"],
        ["clean_orders"],
        run_id="lin-run-1",
    )
    _register(client, "agg_job", ["clean_orders"], ["revenue_dashboard"])

    content = (FIXTURES / "spark_eventlog_failure.jsonl").read_text()
    resp = client.post(
        "/api/v1/orchestration/process/event-log",
        json={"run_id": "lin-run-1", "content": content},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()

    assert report["outcome"] == "needs_approval"
    assert report["blast_radius"] is not None
    impacted = {i["name"] for i in report["blast_radius"]["impacted"]}
    # clean_orders is the run's output; revenue_dashboard is downstream of it.
    assert "revenue_dashboard" in impacted


def test_report_without_lineage_has_no_blast_radius(client: TestClient) -> None:
    content = (FIXTURES / "spark_eventlog_failure.jsonl").read_text()
    resp = client.post(
        "/api/v1/orchestration/process/event-log",
        json={"run_id": "lin-run-2", "content": content},
    )
    assert resp.status_code == 200
    assert resp.json()["blast_radius"] is None


def test_neighbors_direction_validation(client: TestClient) -> None:
    resp = client.get("/api/v1/metadata/lineage/x/neighbors?direction=sideways")
    assert resp.status_code == 422
