#!/bin/bash
set -e

# -- Helper: Wait for a service to be ready
wait_for_service(){
    local host="$1"
    local port="$2"
    local name="$3"
    echo "Waiting for $name ($host:$port)..."

    # Try to connect every 2 seconds
    while ! timeout 1s bash -c "echo > /dev/tcp/$host/$port" 2>/dev/null; do
        echo " $name is not ready yet - retrying..."
        sleep 2
    done
    echo " $name is up!"
}

# 1. Essential Environment Setup
export PYTHONUNBUFFERED=1

# 2. Run Wait Checks (Only if hosts are defined)
if [ -n "$POSTGRES_HOST" ]; then
    wait_for_service "$POSTGRES_HOST" "${POSTGRES_PORT:-5432}" "PostgreSQL"
fi

if [ -n "$MINIO_HOST" ]; then
    wait_for_service "$MINIO_HOST" "${MINIO_PORT:-9000}" "MinIO"
fi

# 3. Handle Process Types
PROCESS_TYPE=${1:-api}

case "$PROCESS_TYPE" in
    "api")
        echo "Starting Production API..."
        
        WORKERS=4

        exec gunicorn app.main:app \
            --workers $WORKERS \
            --worker-class uvicorn.workers.UvicornWorker \
            --bind 0.0.0.0:8001 \
            --access-logfile - \
            --error-logfile - \
            --timeout 120 \
            --keep-alive 5 \
            --reload
        ;;
    "workers")
        echo "Starting Background Worker..."
        # exec python -m app.worker
        ;;
    "migration")
        echo "Running Database Migrations..."
        # exec alembic upgrade head
        ;;
    *)
        echo "Unknown command: $PROCESS_TYPE"
        exec "$@"
        ;;
esac