#!/usr/bin/env sh
# Ingestion gate for Linux / macOS / Unix schedulers (cron, Control-M, Informatica post-session command,
# Ab Initio Run Program component, Autosys). Exit code 1 stops the downstream job.
set -eu
BATCH_ID="${1:-batch-001}"
cd "$(dirname "$0")/.."
odcr run --contract-id orders --connection main --batch-id "$BATCH_ID" \
  --where "load_id = '${BATCH_ID}'" --pipeline orders --stage ingestion
