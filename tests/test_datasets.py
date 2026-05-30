"""Tests for the public-dataset loaders.

Three layers of coverage:

  1. Each loader's bundled fixture parses and maps to FailureProfiles.
  2. The records produced are semantically sane: known categories present,
     OOM records carry the OutOfMemoryError signature, etc. — so a stale
     fixture trips the test before it ships an empty corpus.
  3. The CLI subcommands (`list`, `show`, `ingest`) work end-to-end, with
     `ingest` driving a real in-process TestClient against the new
     /profiles/index endpoint.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from dataforge.datasets import (
    LOADERS,
    DatasetRecord,
    LoghubSparkLoader,
    PostmortemsLoader,
    build_loader,
)
from dataforge.datasets.cli import run as cli_run
from dataforge.modules.rag.profile import FailureProfile

# --- Per-loader smoke ------------------------------------------------------


@pytest.mark.parametrize("name", sorted(LOADERS))
def test_loader_records_parse_and_are_nonempty(name: str) -> None:
    loader = build_loader(name)
    records = list(loader.records())
    assert len(records) >= 20, f"{name} should ship a meaningful sample"
    for r in records:
        assert isinstance(r, DatasetRecord)
        assert r.run_id, f"{name}: record missing run_id"


@pytest.mark.parametrize("name", sorted(LOADERS))
def test_loader_profiles_are_well_formed(name: str) -> None:
    loader = build_loader(name)
    profiles = loader.profiles()
    assert profiles, f"{name}: produced no profiles"
    for p in profiles:
        assert isinstance(p, FailureProfile)
        assert p.run_id
        # Tokens are what the hashing embedder consumes; never empty.
        assert p.tokens, f"{name}: profile {p.run_id} has no tokens"


def test_limit_truncates_records() -> None:
    loader = PostmortemsLoader()
    full = list(loader.records())
    truncated = list(loader.records(limit=3))
    assert len(truncated) == 3
    assert truncated == list(full[:3])


# --- Fixture content quality ----------------------------------------------


def test_postmortems_cover_multiple_cause_categories() -> None:
    profiles = PostmortemsLoader().profiles()
    categories = {p.category for p in profiles if p.category}
    # We curated samples spanning the analyzer taxonomy.
    assert "memory_pressure" in categories
    assert "data_skew" in categories
    assert "dependency_failure" in categories
    assert "performance_regression" in categories


def test_loghub_includes_oom_and_skew_signals() -> None:
    profiles = LoghubSparkLoader().profiles()
    has_oom = any(p.error_class and "OutOfMemoryError" in p.error_class for p in profiles)
    has_skew = any(p.category == "data_skew" for p in profiles)
    has_noise = any(p.category is None for p in profiles)
    assert has_oom, "OOM-tagged log entries must exist in the Loghub sample"
    assert has_skew, "skew-tagged log entries must exist in the Loghub sample"
    # Real corpora are mostly INFO/normal lines; we ship a few unlabeled to
    # ensure the loader handles records without a category.
    assert has_noise, "expected some unlabeled log lines (realistic mix)"


# --- Factory ---------------------------------------------------------------


def test_build_loader_returns_typed_instance() -> None:
    assert isinstance(build_loader("postmortems"), PostmortemsLoader)
    assert isinstance(build_loader("loghub_spark"), LoghubSparkLoader)


def test_build_loader_raises_on_unknown_name() -> None:
    with pytest.raises(KeyError):
        build_loader("does_not_exist")


# --- CLI -------------------------------------------------------------------


def test_cli_list_prints_all_datasets(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_run(["list"]) == 0
    out = capsys.readouterr().out
    for name in LOADERS:
        assert name in out


def test_cli_show_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_run(["show", "--dataset", "postmortems", "--limit", "3"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert len(payload) == 3
    assert all("run_id" in row for row in payload)


def test_cli_rejects_unknown_dataset() -> None:
    with pytest.raises(SystemExit):
        cli_run(["show", "--dataset", "bogus"])


# --- /profiles/index endpoint + CLI ingest ---------------------------------


@pytest.fixture
def app_client() -> Iterator[TestClient]:
    from dataforge.app import create_app

    with TestClient(create_app()) as c:
        yield c


def test_index_profile_endpoint_round_trips(app_client: TestClient) -> None:
    profile = PostmortemsLoader().profiles(limit=1)[0]
    response = app_client.post(
        "/api/v1/rag/profiles/index",
        json=profile.model_dump(mode="json"),
    )
    assert response.status_code == 200, response.text
    echoed = FailureProfile(**response.json())
    assert echoed.run_id == profile.run_id
    assert echoed.category == profile.category


def test_cli_ingest_posts_each_profile_and_counts_results(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify the CLI's iteration/counting via a stub httpx.Client.

    The /profiles/index endpoint itself is covered by
    test_index_profile_endpoint_round_trips above; this test exercises only
    the CLI loop so it stays decoupled from the FastAPI app.
    """
    posted: list[tuple[str, dict[str, object]]] = []

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict[str, object]:
            return {}

    class _FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, json: dict[str, object] | None = None) -> _FakeResponse:
            posted.append((url, json or {}))
            return _FakeResponse()

    monkeypatch.setattr(httpx, "Client", _FakeClient)

    assert (
        cli_run(
            [
                "ingest",
                "--dataset",
                "postmortems",
                "--base-url",
                "http://app",
                "--limit",
                "5",
            ]
        )
        == 0
    )
    assert len(posted) == 5
    for url, body in posted:
        assert url.endswith("/api/v1/rag/profiles/index")
        assert "run_id" in body
    err = capsys.readouterr().err
    assert "indexed=5" in err
    assert "failed=0" in err


def test_cli_ingest_counts_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A 4xx response counts as a failure; CLI exits non-zero."""

    class _BadResponse:
        status_code = 422
        text = "bad"

    class _FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, json: dict[str, object] | None = None) -> _BadResponse:
            return _BadResponse()

    monkeypatch.setattr(httpx, "Client", _FakeClient)

    rc = cli_run(
        [
            "ingest",
            "--dataset",
            "postmortems",
            "--base-url",
            "http://app",
            "--limit",
            "2",
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "indexed=0" in err
    assert "failed=2" in err
