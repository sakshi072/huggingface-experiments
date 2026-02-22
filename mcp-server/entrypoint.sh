#!/bin/bash
# entrypoint.sh
set -e

PORT=${PORT:-8002}

echo "Starting MCP tool server..."

exec gunicorn mcp_server.main:app \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:$PORT" \
    --timeout 120 \
    --keep-alive 65 \
    --access-logfile - \
    --error-logfile -