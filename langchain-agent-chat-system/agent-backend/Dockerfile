# langchain-agent-chat-system/agent-backend/Dockerfile

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn uvicorn[standard]

# Install LangChain with compatible versions
RUN pip install --no-cache-dir \
    langchain \
    langchain-openai \
    langchain-community \
    langchain-core \
    langchain-text-splitters \
    langchain-classic \
    langfuse \
    langchain-ollama

# Verify critical packages are installed
RUN python -c "import fastapi; import uvicorn; import pymongo; import openai; print('✅ All packages installed')"
# Copy application code
COPY . .

# Ensure uvicorn is in the path
ENV PATH="/home/user/.local/bin:${PATH}"

# Create non-root user (matches K8s securityContext runAsUser: 1000)
RUN chmod +x /app/entrypoint.sh && \     
    groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=300s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["/app/entrypoint.sh"]