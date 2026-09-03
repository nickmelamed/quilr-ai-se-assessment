#!/usr/bin/env bash
# Starts the mock downstream MCP server and the gateway proxy with one command.
set -euo pipefail
cd "$(dirname "$0")"

uvicorn downstream_server:app --port 8100 &
DOWNSTREAM_PID=$!
trap 'kill $DOWNSTREAM_PID 2>/dev/null' EXIT

for _ in $(seq 1 20); do
    if curl -s -o /dev/null "http://localhost:8100/docs"; then
        break
    fi
    sleep 0.25
done

echo "Downstream MCP server running on :8100 (pid $DOWNSTREAM_PID)"
echo "Starting gateway proxy on :8000 ..."
uvicorn gateway:app --port 8000
