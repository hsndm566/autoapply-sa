#!/bin/bash
# docker-start.sh — boots n8n, imports workflows, runs sender in background
set -e

# start n8n
echo "=== starting n8n ==="
n8n start --port 5678 > /tmp/n8n.log 2>&1 &
N8N_PID=$!

# wait for n8n, then import workflows
echo "=== waiting for n8n + importing workflows ==="
for i in $(seq 1 30); do
  if curl -s http://localhost:5678/healthz >/dev/null 2>&1; then
    echo "n8n up — importing /workflows"
    n8n import:workflow --input=/workflows --separate >> /tmp/n8n-import.log 2>&1 && echo "WORKFLOWS IMPORTED" || echo "IMPORT ERROR"
    break
  fi
  echo "n8n not ready ($i/30)..."
  sleep 5
done

# run sender loop in background (keeps emails flowing off-laptop)
echo "=== starting sender ==="
cd /home/node/.n8n
python3 cloud_loop.py > /tmp/sender.log 2>&1 &

# keep container alive by waiting on n8n
wait $N8N_PID
