"""Simulator CLI.

Usage::

    # Enumerate available scenarios.
    python -m dataforge.simulator --list

    # Print a scenario's JSONL event log to stdout.
    python -m dataforge.simulator --scenario oom_join --run-id sim-001

    # Write to a file.
    python -m dataforge.simulator --scenario data_skew --run-id sim-002 -o out.jsonl

    # Drive the full self-healing loop against a running app (requires the
    # API to be up; calls the orchestration coordinator endpoint).
    python -m dataforge.simulator --scenario oom_join --run-id sim-003 \\
        --ingest-url http://localhost:8000

Network calls use the httpx client already in core deps; no extras needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from dataforge.simulator.scenarios import (
    SCENARIOS,
    build_scenario,
    events_to_jsonl,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataforge.simulator",
        description="Generate Spark event-log JSONL for canned chaos scenarios.",
    )
    parser.add_argument("--list", action="store_true", help="List available scenarios and exit.")
    parser.add_argument(
        "--scenario",
        help=f"Scenario name. One of: {', '.join(SCENARIOS)}.",
    )
    parser.add_argument(
        "--run-id",
        help="Run identifier embedded in the event log (e.g. sim-001).",
    )
    parser.add_argument(
        "--app-name",
        default=None,
        help="Override the default Spark app name for the scenario.",
    )
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=None,
        help="Override the default number of tasks the scenario emits.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Write JSONL to this path (default: stdout). Use '-' for stdout.",
    )
    parser.add_argument(
        "--ingest-url",
        default=None,
        help=(
            "Base URL of a running DataForge API. When set, the JSONL is "
            "POSTed to /api/v1/orchestration/process/event-log so the full "
            "self-healing loop runs end-to-end."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds when ingesting (default: 60).",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Entry point for the CLI. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list:
        for name, scenario in SCENARIOS.items():
            print(f"{name}: {scenario.description}")
        return 0

    if not args.scenario or not args.run_id:
        parser.error("--scenario and --run-id are required (or pass --list)")

    if args.scenario not in SCENARIOS:
        parser.error(f"unknown scenario '{args.scenario}'. " f"Known: {', '.join(SCENARIOS)}.")

    events = build_scenario(
        args.scenario,
        run_id=args.run_id,
        app_name=args.app_name,
        num_tasks=args.num_tasks,
    )
    content = events_to_jsonl(events)

    if args.ingest_url:
        return _ingest(
            base_url=args.ingest_url,
            run_id=args.run_id,
            content=content,
            timeout=args.timeout,
        )

    if args.output and args.output != "-":
        Path(args.output).write_text(content)
        print(f"wrote {len(events)} events to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(content)
    return 0


def _ingest(*, base_url: str, run_id: str, content: str, timeout: float) -> int:
    url = base_url.rstrip("/") + "/api/v1/orchestration/process/event-log"
    try:
        response = httpx.post(
            url,
            json={"run_id": run_id, "content": content},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        print(f"ingest failed: {exc}", file=sys.stderr)
        return 2
    if response.status_code >= 400:
        print(
            f"ingest returned {response.status_code}: {response.text[:500]}",
            file=sys.stderr,
        )
        return 2
    json.dump(response.json(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0
