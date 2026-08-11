#!/bin/bash
# start.sh — boots n8n (imports AutoApply workflows) + runs the gated sender loop.
set -e

# start n8n in background
echo "=== starting n8n ==="
n8n start --port 5678 > /tmp/n8n.log 2>&1 &
N8N_PID=$!

# wait for n8n to be ready, then import workflows
echo "=== waiting for n8n, then importing workflows ==="
for i in $(seq 1 30); do
  if curl -s http://localhost:5678/healthz >/dev/null 2>&1; then
    echo "n8n is up — importing workflows from /workflows"
    n8n import:workflow --input=/workflows --separate >> /tmp/n8n-import.log 2>&1 && echo "WORKFLOWS IMPORTED" || echo "IMPORT ERROR (see /tmp/n8n-import.log)"
    break
  fi
  echo "n8n not ready ($i/30)..."
  sleep 5
done

# run the gated sender loop in foreground (keeps container alive)
echo "=== starting cloud_loop sender ==="
python cloud_loop.py
