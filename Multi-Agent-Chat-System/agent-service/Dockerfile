# Day2-hands-on/hf_backend/Dockerfile

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
    pip install --no-cache-dir -r requirements.txt

# Install uvicorn explicitly (if not in requirements.txt)
RUN pip install --no-cache-dir uvicorn[standard]

# Install LangChain with compatible versions
RUN pip install --no-cache-dir \
    langchain \
    langchain-openai \
    langchain-community \
    langchain-core \
    langchain-text-splitters \
    langchain-classic

# Verify critical packages are installed
RUN python -c "import fastapi; import uvicorn; import pymongo; import openai; print('✅ All packages installed')"
# Copy application code
COPY . .

# Ensure uvicorn is in the path
ENV PATH="/home/user/.local/bin:${PATH}"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "hf_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]