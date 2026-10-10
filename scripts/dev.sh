#!/usr/bin/env bash
# Run the whole RiskDiff demo locally: FastAPI on :8000 and Next.js on :3000.
# Usage: ./scripts/dev.sh            (Ctrl-C stops both)
#        RISKDIFF_SHOW_FIXTURE=1 ./scripts/dev.sh   to also list the synthetic FIXTURE company
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "note: no .env found. Copy .env.example to .env and set SEC_USER_AGENT (and HF_TOKEN) to analyze real tickers." >&2
fi
if [ ! -d .venv ]; then uv sync; fi
if [ ! -d web/node_modules ]; then (cd web && npm install); fi

export RISKDIFF_ALLOW_FIXTURE="${RISKDIFF_ALLOW_FIXTURE:-${RISKDIFF_SHOW_FIXTURE:-0}}"
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT INT TERM
(cd web && RISKDIFF_SHOW_FIXTURE="${RISKDIFF_SHOW_FIXTURE:-0}" npm run dev)
