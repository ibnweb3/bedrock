#!/bin/sh
# Container entrypoint: FalkorDB (redis-server + falkordb.so) and the audit web app in one container.
# Redis listens on 127.0.0.1 only; only the web port is reachable from outside.
set -eu

PORT="${PORT:-8765}"
export FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6379 FALKORDB_GRAPH="${FALKORDB_GRAPH:-bedrock}"

redis-server --bind 127.0.0.1 --port 6379 --protected-mode yes --save "" --appendonly no --dir /tmp \
    --loadmodule /var/lib/falkordb/bin/falkordb.so ${BEDROCK_FALKORDB_ARGS:-THREAD_COUNT 2 MAX_QUEUED_QUERIES 25 RESULTSET_SIZE 10000} &

# Load the published slim graph in the background so the web port opens immediately
# (/api/health answers 503 "not ready" until the graph is in place).
python scripts/snapshot.py restore --graph "$FALKORDB_GRAPH" --wait 60 &

exec python scripts/serve.py --host 0.0.0.0 --port "$PORT"
