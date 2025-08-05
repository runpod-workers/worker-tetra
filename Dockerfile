FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime AS builder

WORKDIR /app

# Install build tools and uv (only in builder stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential ca-certificates \
 && curl -LsSf https://astral.sh/uv/install.sh | sh \
 && cp ~/.local/bin/uv /usr/local/bin/uv \
 && chmod +x /usr/local/bin/uv

# Copy app code and install dependencies
COPY README.md src/* pyproject.toml uv.lock test_*.json ./
RUN uv sync


# --- Final stage: strip build tools, retain only runtime essentials ---
FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Copy app and uv binary from builder
COPY --from=builder /app /app
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Clean up any unnecessary system tools
RUN rm -rf /var/lib/apt/lists/*

CMD ["uv", "run", "handler.py"]