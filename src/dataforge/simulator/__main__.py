"""Entry point so `python -m dataforge.simulator ...` works."""

from __future__ import annotations

import sys

from dataforge.simulator.cli import run

if __name__ == "__main__":
    sys.exit(run())
