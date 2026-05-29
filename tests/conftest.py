"""Shared pytest fixtures.

Tests run against a file-backed SQLite database via aiosqlite so the full
parse -> persist -> read path is exercised without requiring a Postgres
container. The DSN is set before the app (and its cached settings) load.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _configure_test_db(tmp_path_factory: pytest.TempPathFactory) -> None:
    db_path: Path = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DATAFORGE_POSTGRES_DSN"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DATAFORGE_ENVIRONMENT"] = "local"
    os.environ["DATAFORGE_TRACING_ENABLED"] = "false"
    os.environ["DATAFORGE_METRICS_ENABLED"] = "false"
    # Reset any cached settings so the test DSN takes effect.
    from dataforge.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from dataforge.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def db_session() -> AsyncIterator[object]:
    """A standalone session with tables created, for repository unit tests."""
    from dataforge.core.db import Base, get_engine, session_scope
    from dataforge.modules.metadata import models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_scope() as session:
        yield session
