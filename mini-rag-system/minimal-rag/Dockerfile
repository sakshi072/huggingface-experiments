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
RUN poetry install --no-interaction --no-ansi --no-root

# Verify critical packages are installed
RUN python -c "import fastapi; import uvicorn; print('All packages installed')"

# Copy application code
COPY . .

# 1. Make the entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# 2. Use the script as the entrypoint
# This allows you to pass arguments to the script via 'docker run'
ENTRYPOINT ["/app/entrypoint.sh"]

# 3. Default argument passed to the ENTRYPOINT
CMD ["api"]

# # Expose port
# EXPOSE 8001

# # Health check
# HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
#     CMD curl -f http://localhost:8001/health || exit 1

# # Run the application
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]