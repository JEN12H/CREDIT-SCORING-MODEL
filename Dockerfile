
# BAAKI Credit Scoring — Production Dockerfile
# Multi-stage build for minimal image size.
#
# Build:  docker build -t baaki-scoring .
# Run:    docker run -p 8000:8000 --env-file .env baaki-scoring


FROM python:3.9-slim AS builder

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Runtime image ─────────────────────────────────────────
FROM python:3.9-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Create data and models directories
RUN mkdir -p data models

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start the API server
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
