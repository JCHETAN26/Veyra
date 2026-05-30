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
    """An isolated in-memory session with fresh tables, for repository tests.

    Uses its own engine (not the shared app DB) so repository unit tests that
    assert exact contents aren't polluted by other tests sharing the file DB.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from dataforge.core.db import Base
    from dataforge.modules.metadata import models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        finally:
            await session.close()
    await engine.dispose()
