#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PORT="${TRACE_VIEWER_PORT:-8501}"
echo "Starting NovaMart AI Trace Explorer (Streamlit) on http://127.0.0.1:${PORT} ..."

exec "${SCRIPT_DIR}/backend/.venv/bin/streamlit" run "${SCRIPT_DIR}/trace_viewer/app.py" \
  --server.port "${PORT}" \
  --server.address 127.0.0.1 \
  --browser.gatherUsageStats false
