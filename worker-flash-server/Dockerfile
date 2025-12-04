# Flash Server Dockerfile
# Pre-built image for CPU Flash Server deployment
# Downloads project tarball from S3 and runs FastAPI server

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Install core dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    tetra-rp \
    boto3

# Copy server code
COPY src/ /app/

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start server
CMD ["python", "server.py"]
