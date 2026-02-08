# =============================================================================
# Dockerfile for RAG API - Simplified Build
# =============================================================================
# AI Learning Note:
# This simplified Dockerfile installs only essential dependencies
# to reduce build size and time. For production, consider multi-stage builds.
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Security: Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Install core Python dependencies only (no heavy ML libraries for initial deploy)
COPY requirements-minimal.txt ./
RUN pip install --no-cache-dir -r requirements-minimal.txt

# Copy application code
COPY src/ ./src/

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.rag_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
