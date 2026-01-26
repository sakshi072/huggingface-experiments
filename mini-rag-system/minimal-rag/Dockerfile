FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to not create virtual environment (we're in container)
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi --no-root && \
    rm -rf /root/.cache/pypoetry && \
    rm -rf /root/.cache/pip

# Verify critical packages are installed
RUN python -c "import fastapi; import uvicorn; print('All packages installed')"

# Pre-download embedding model (avoids runtime download)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Create non-root user (matches K8s securityContext runAsUser: 1000)
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

# Copy application code
COPY --chown=appuser:appgroup . .

# 1. Make the entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# 2. Use the script as the entrypoint
# This allows you to pass arguments to the script via 'docker run'
ENTRYPOINT ["/app/entrypoint.sh"]

# Switch to non-root user
USER appuser

# 3. Default argument passed to the ENTRYPOINT
CMD ["api"]

# # Expose port
# EXPOSE 8001

# # Health check
# HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
#     CMD curl -f http://localhost:8001/health || exit 1

# # Run the application
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]