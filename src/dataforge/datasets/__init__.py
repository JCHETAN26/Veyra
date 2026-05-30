"""Public-dataset loaders for the operational RAG corpus.

Each loader produces a list of :class:`FailureProfile` records ready to be
indexed by the RAG service. Bundled samples ship in the package so demos
and CI work offline; live-fetch from upstream is a planned follow-on
behind the same loader interface.

Currently shipped:

  - postmortems     -> curated public-incident references
                       (style: danluu/post-mortems)
  - loghub_spark    -> Spark log lines with anomaly hints
                       (style: logpai/loghub Spark dataset)
"""

from __future__ import annotations

from dataforge.datasets.factory import LOADERS, build_loader
from dataforge.datasets.loader import DatasetLoader, DatasetRecord
from dataforge.datasets.loghub_spark import LoghubSparkLoader
from dataforge.datasets.postmortems import PostmortemsLoader

__all__ = [
    "LOADERS",
    "DatasetLoader",
    "DatasetRecord",
    "LoghubSparkLoader",
    "PostmortemsLoader",
    "build_loader",
]
