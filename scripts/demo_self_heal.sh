#!/usr/bin/env bash
# Drive the DataForge self-healing loop end-to-end against a running app.
#
# Walks through:
#   1. seeding a small operational history (so RAG has something to retrieve),
#   2. injecting a NEW OOM failure via the chaos simulator,
#   3. detecting it, explaining the root cause, retrieving similar past
#      incidents, and proposing a fix (gated on human approval),
#   4. approving the proposal,
#   5. confirming the workflow resolved.
#
# Defaults to the deterministic rule-based path so this works key-less. With
# DATAFORGE_LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY set in the app's
# environment, the RCA + fix proposal arrive as full LLM-generated structured
# output — same script, richer payloads.
#
# Usage:
#   scripts/demo_self_heal.sh [--base-url URL] [--start-app] [--dry-run]
#
#   --base-url URL    API base URL (default: http://localhost:8000)
#   --start-app       Run `docker compose up -d app` first and wait for ready
#   --dry-run         Print steps without making requests
#   -h, --help        Show this help

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
START_APP=0
DRY_RUN=0

usage() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-url) BASE_URL="$2"; shift 2;;
        --start-app) START_APP=1; shift;;
        --dry-run) DRY_RUN=1; shift;;
        -h|--help) usage; exit 0;;
        *) echo "unknown arg: $1" >&2; usage; exit 2;;
    esac
done

# Pretty-print JSON: jq if available, else stdlib.
if command -v jq >/dev/null 2>&1; then
    pp() { jq "$@"; }
else
    pp() { python -m json.tool; }
fi

section() {
    printf '\n'
    printf '════════════════════════════════════════════════════════════════════════\n'
    printf '  %s\n' "$1"
    printf '════════════════════════════════════════════════════════════════════════\n'
}

wait_ready() {
    local url="$1/health/ready"
    for _ in $(seq 1 60); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "API at $1 did not become ready within 60s" >&2
    return 1
}

# Inject a scenario through the orchestration coordinator endpoint, which runs
# the full self-healing loop (ingest -> detect -> RCA -> RAG -> propose) and
# returns a single PipelineReport.
inject() {
    local scenario="$1"
    local run_id="$2"
    if [[ $DRY_RUN -eq 1 ]]; then
        printf '[dry-run] inject scenario=%s run_id=%s\n' "$scenario" "$run_id" >&2
        printf '{"outcome":"dry_run"}\n'
        return 0
    fi
    uv run python -m dataforge.simulator \
        --scenario "$scenario" \
        --run-id "$run_id" \
        --ingest-url "$BASE_URL"
}

approve() {
    local run_id="$1"
    if [[ $DRY_RUN -eq 1 ]]; then
        printf '[dry-run] approve run_id=%s\n' "$run_id" >&2
        printf '{"state":"resolved"}\n'
        return 0
    fi
    curl -fsS -X POST \
        -H 'Content-Type: application/json' \
        -d '{"approver": "demo-engineer"}' \
        "$BASE_URL/api/v1/orchestration/runs/$run_id/remediation/approve"
}

if [[ $START_APP -eq 1 ]]; then
    section "Starting app via docker compose"
    if [[ $DRY_RUN -eq 0 ]]; then
        docker compose up -d app
        wait_ready "$BASE_URL"
    else
        echo "[dry-run] docker compose up -d app"
    fi
fi

DEMO_RUN_ID="demo-$(date +%s)"

section "1/6  Seeding operational history (3 prior runs)"
inject "data_skew"           "hist-skew-$(date +%s)"   | pp '{outcome, run_id}' || true
inject "schema_drift"        "hist-drift-$(date +%s)"  | pp '{outcome, run_id}' || true
inject "oom_join"            "hist-oom-$(date +%s)"    | pp '{outcome, run_id}' || true

section "2/6  Injecting NEW failure: oom_join (run_id=$DEMO_RUN_ID)"
REPORT="$(inject 'oom_join' "$DEMO_RUN_ID")"
echo "$REPORT" | pp '{outcome, incidents_count: (.incidents | length), cause: .analysis.category, similar_count: (.similar_incidents | length)}'

section "3/6  Root-cause analysis"
echo "$REPORT" | pp '.analysis | {category, summary, explanation, confidence, analyzer}'

section "4/6  Similar past incidents (top-K from RAG)"
echo "$REPORT" | pp '.similar_incidents | map({run_id, score, category, summary})'

section "5/6  Fix proposal (pending human approval)"
echo "$REPORT" | pp '.workflow.proposal | {cause_category, confidence, actions: (.actions | map({title, kind, parameters, confidence, rollback, estimated_impact}))}'

section "6/6  Approving the fix → executing fallback chain"
APPROVAL="$(approve "$DEMO_RUN_ID")"
echo "$APPROVAL" | pp '{state, applied_action_index, attempts, applied_action: (if .applied_action_index != null then .proposal.actions[.applied_action_index].title else null end)}'

section "✓ Demo complete"
echo "Run inspected: $DEMO_RUN_ID"
echo "Final state: $(echo "$APPROVAL" | pp -r '.state' 2>/dev/null || echo "see above")"
