"""Datasets CLI.

Usage::

    # Enumerate shipped datasets.
    python -m dataforge.datasets list

    # Preview the first 5 records as JSON.
    python -m dataforge.datasets show --dataset postmortems --limit 5

    # Ingest all records into a running app's RAG corpus.
    python -m dataforge.datasets ingest \\
        --dataset postmortems \\
        --base-url http://localhost:8000

When `--base-url` is reachable, each record is sent through
/api/v1/rag/runs/<run_id>/index so the corpus is populated through the
public API rather than reaching directly into the in-process store. The
running app must be configured with the embedder you want (hashing or
semantic) — the loader doesn't care.
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

from dataforge.datasets.factory import LOADERS, build_loader


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataforge.datasets",
        description="Load public-incident corpora into the RAG index.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List available datasets.")

    show = sub.add_parser("show", help="Print records as JSON (no network).")
    show.add_argument("--dataset", required=True, choices=sorted(LOADERS))
    show.add_argument("--limit", type=int, default=None)

    ingest = sub.add_parser(
        "ingest",
        help="POST each record's profile into a running RAG corpus.",
    )
    ingest.add_argument("--dataset", required=True, choices=sorted(LOADERS))
    ingest.add_argument("--base-url", required=True)
    ingest.add_argument("--limit", type=int, default=None)
    ingest.add_argument("--timeout", type=float, default=60.0)

    return parser


def run(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for name, cls in sorted(LOADERS.items()):
            print(f"{name}: {cls().description}")
        return 0

    if args.cmd == "show":
        loader = build_loader(args.dataset)
        records = loader.records(limit=args.limit)
        json.dump([r.model_dump() for r in records], sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.cmd == "ingest":
        return _ingest(
            dataset=args.dataset,
            base_url=args.base_url,
            limit=args.limit,
            timeout=args.timeout,
        )

    parser.error(f"unknown subcommand: {args.cmd}")
    return 2  # unreachable; argparse already exited.


def _ingest(*, dataset: str, base_url: str, limit: int | None, timeout: float) -> int:
    loader = build_loader(dataset)
    profiles = loader.profiles(limit=limit)

    base = base_url.rstrip("/")
    url = f"{base}/api/v1/rag/profiles/index"
    indexed = 0
    failed = 0
    with httpx.Client(timeout=timeout) as client:
        for p in profiles:
            try:
                response = client.post(url, json=p.model_dump(mode="json"))
            except httpx.HTTPError as exc:
                print(f"  ! {p.run_id}: {exc}", file=sys.stderr)
                failed += 1
                continue
            if response.status_code >= 400:
                print(
                    f"  ! {p.run_id}: {response.status_code} {response.text[:200]}",
                    file=sys.stderr,
                )
                failed += 1
                continue
            indexed += 1

    print(
        f"dataset={dataset} indexed={indexed} failed={failed} total={indexed + failed}",
        file=sys.stderr,
    )
    return 0 if failed == 0 else 1
