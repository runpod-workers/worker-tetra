FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime

WORKDIR /app

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
# Set timezone to avoid tzdata prompts
ENV TZ=Etc/UTC

# Enable HuggingFace transfer acceleration
ENV HF_HUB_ENABLE_HF_TRANSFER=1
# Relocate HuggingFace cache outside /root/.cache to exclude from volume sync
ENV HF_HOME=/hf-cache

# Configure APT cache to persist under /root/.cache for volume sync
RUN mkdir -p /root/.cache/apt/archives/partial \
 && echo 'Dir::Cache "/root/.cache/apt";' > /etc/apt/apt.conf.d/01cache

# Install system dependencies and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates nala \
 && curl -LsSf https://astral.sh/uv/install.sh | sh \
 && cp ~/.local/bin/uv /usr/local/bin/uv \
 && chmod +x /usr/local/bin/uv \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Copy app code and install dependencies
COPY README.md pyproject.toml uv.lock ./
COPY src/ ./
RUN uv export --format requirements-txt --no-dev --no-hashes > requirements.txt \
 && uv pip install --system -r requirements.txt

CMD ["python", "handler.py"]
