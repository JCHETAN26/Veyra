"""End-to-end test mirroring `scripts/demo_self_heal.sh`.

Drives the full self-healing loop in-process through the FastAPI app:

  seed history -> inject failure -> verify report shape
  -> approve -> verify resolution

If this test ever fails, the demo script is broken. That's the point.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from dataforge.simulator import build_scenario, events_to_jsonl


@pytest.fixture
def demo_client() -> Iterator[TestClient]:
    """A fresh TestClient bound to a freshly-built app instance."""
    from dataforge.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def _inject(client: TestClient, scenario: str, run_id: str) -> dict[str, object]:
    """Drive a scenario through the orchestration coordinator."""
    content = events_to_jsonl(build_scenario(scenario, run_id=run_id))
    response = client.post(
        "/api/v1/orchestration/process/event-log",
        json={"run_id": run_id, "content": content},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_demo_self_heal_flow_end_to_end(demo_client: TestClient) -> None:
    # --- 1. Seed history -----------------------------------------------
    # Three prior runs in different categories so the corpus has something
    # to surface as "similar" later.
    _inject(demo_client, "data_skew", "demo-e2e-hist-skew")
    _inject(demo_client, "schema_drift", "demo-e2e-hist-drift")
    _inject(demo_client, "oom_join", "demo-e2e-hist-oom")

    # --- 2. Inject the NEW failure -------------------------------------
    demo_id = "demo-e2e-001"
    report = _inject(demo_client, "oom_join", demo_id)

    # --- 3. Report shape -----------------------------------------------
    assert report["outcome"] == "needs_approval"
    assert report["run_id"] == demo_id
    assert isinstance(report["incidents"], list) and len(report["incidents"]) >= 2
    incident_types = {i["anomaly_type"] for i in report["incidents"]}
    assert "run_failure" in incident_types
    assert "excessive_spill" in incident_types

    # --- 4. Root-cause analysis ----------------------------------------
    analysis = report["analysis"]
    assert analysis is not None
    assert analysis["category"] == "memory_pressure"
    assert analysis["confidence"] >= 0.8
    assert analysis["analyzer"].startswith("rule-based")  # null provider path

    # --- 5. Similar past incidents -------------------------------------
    similar = report["similar_incidents"]
    assert isinstance(similar, list)
    # The seeded OOM history should resemble the new OOM run.
    assert any(
        s["run_id"] == "demo-e2e-hist-oom" or s["category"] == "memory_pressure" for s in similar
    ), f"expected an OOM-like prior run in similar_incidents, got {similar}"

    # --- 6. Fix proposal pending approval ------------------------------
    workflow = report["workflow"]
    assert workflow is not None
    assert workflow["state"] == "pending_approval"
    proposal = workflow["proposal"]
    assert proposal["cause_category"] == "memory_pressure"
    assert proposal["actions"], "expected at least one actionable fix"

    # --- 7. Approve & verify resolution --------------------------------
    approve_response = demo_client.post(
        f"/api/v1/orchestration/runs/{demo_id}/remediation/approve",
        json={"approver": "demo-test"},
    )
    assert approve_response.status_code == 200, approve_response.text
    resolved = approve_response.json()

    assert resolved["state"] == "resolved", resolved
    assert resolved["applied_action_index"] is not None
    assert resolved["attempts"] >= 1
    applied = resolved["proposal"]["actions"][resolved["applied_action_index"]]
    # The simulator's OOM run resolves on the broadcast-join or shuffle-
    # partitions fix; both are valid demo outcomes.
    title = applied["title"].lower()
    assert "broadcast" in title or "shuffle partition" in title


def test_demo_healthy_run_yields_no_workflow(demo_client: TestClient) -> None:
    """The healthy scenario should short-circuit before remediation."""
    report = _inject(demo_client, "healthy", "demo-e2e-healthy-001")
    assert report["outcome"] == "healthy"
    assert report["incidents"] == []
    assert report["analysis"] is None
    assert report["workflow"] is None
