"""Foundation tests: health, module mounting, correlation IDs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from dataforge.registry import MODULES


def test_liveness(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_reports_dependencies(client: TestClient) -> None:
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded", "down"}
    # Modules report named dependencies; metadata surfaces its postgres probe.
    reported = {dep["name"] for dep in body["dependencies"]}
    assert "postgres" in reported
    assert len(reported) >= len(MODULES) - 1


def test_every_module_status_endpoint_mounts(client: TestClient) -> None:
    for mod in MODULES:
        resp = client.get(f"/api/v1/{mod.name}/status")
        assert resp.status_code == 200, mod.name
        assert resp.json()["module"] == mod.name


def test_correlation_id_echoed_in_response(client: TestClient) -> None:
    resp = client.get("/health/live", headers={"x-correlation-id": "test-123"})
    assert resp.headers["x-correlation-id"] == "test-123"
    assert "x-request-id" in resp.headers


def test_correlation_id_generated_when_absent(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.headers.get("x-request-id")
    assert resp.headers.get("x-correlation-id")
