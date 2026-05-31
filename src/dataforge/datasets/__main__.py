"""Entry point so `python -m dataforge.datasets ...` works."""

from __future__ import annotations

import sys

from dataforge.datasets.cli import run

if __name__ == "__main__":
    sys.exit(run())
