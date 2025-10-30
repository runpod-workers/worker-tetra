# Worker Flash Server

Pre-built Docker image for Flash Server (CPU serverless endpoint).

## Features

- Downloads project tarball from S3 on startup
- Extracts full project code (with `@remote` decorators)
- Starts FastAPI server
- Handles GPU worker deployment via `@remote` decorator

## Build

```bash
docker build -t runpod/flash-server:latest .
```

