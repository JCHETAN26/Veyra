"""Loader factory + registry.

Single place that knows the set of shipped loaders. Callers (the CLI and
tests) look up by name; adding a new loader is a one-line change here.
"""

from __future__ import annotations

from dataforge.datasets.loader import DatasetLoader
from dataforge.datasets.loghub_spark import LoghubSparkLoader
from dataforge.datasets.postmortems import PostmortemsLoader


def _build_postmortems() -> DatasetLoader:
    return PostmortemsLoader()


def _build_loghub_spark() -> DatasetLoader:
    return LoghubSparkLoader()


LOADERS: dict[str, type[DatasetLoader]] = {
    "postmortems": PostmortemsLoader,
    "loghub_spark": LoghubSparkLoader,
}


def build_loader(name: str) -> DatasetLoader:
    """Construct the loader for `name`, or raise KeyError."""
    cls = LOADERS[name]
    return cls()
