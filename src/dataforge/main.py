"""Uvicorn entrypoint.

Run locally with:  uv run uvicorn dataforge.main:app --reload
Or via the console / Docker with the module path dataforge.main:app
"""

from __future__ import annotations

from dataforge.app import create_app

app = create_app()
