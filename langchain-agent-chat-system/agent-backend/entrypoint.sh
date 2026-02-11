#!/bin/bash
# entrypoint.sh
set -e

WORKERS=${WORKER_COUNT:-3}

echo "Starting Langchain Backend server with $WORKERS workers..."

exec gunicorn app.main:app \
    --workers "$WORKERS" \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --keep-alive 5 \
    --preload \
    --access-logfile - \
    --error-logfile -