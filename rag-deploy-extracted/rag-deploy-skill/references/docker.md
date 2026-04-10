# Docker Templates for RAG Deployment

## Backend Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps required for HuggingFace sentence-transformers
RUN apt-get update && apt-get install -y \
    build-essential \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache — only rebuilds when requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source code
COPY . .

# HuggingFace model cache — must match volume mount in docker-compose
ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 1 worker only — HF models are ~1GB, multiple workers = OOM on 4GB VPS
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

## .dockerignore

```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.egg-info/
.env
.env.*
!.env.example
.git/
.gitignore
*.md
data/
models/
.pytest_cache/
.mypy_cache/
node_modules/
frontend/node_modules/
frontend/.next/
*.log
```

## docker-compose.yml (full — no Redis)

```yaml
version: "3.9"

services:

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./frontend/dist:/usr/share/nginx/html:ro
    depends_on:
      - backend
    restart: unless-stopped

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    env_file: .env
    expose:
      - "8000"
    volumes:
      - hf_models:/app/models      # Named volume — HF models survive redeploys
    depends_on:
      - qdrant
      - postgres
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s            # Give time for HF model loading

  qdrant:
    image: qdrant/qdrant:latest
    expose:
      - "6333"
    volumes:
      - ./data/qdrant:/qdrant/storage
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 20s
      timeout: 5s
      retries: 3

  postgres:
    image: postgres:16-alpine
    env_file: .env
    expose:
      - "5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5

  pgadmin:
    image: dpage/pgadmin4:latest
    ports:
      - "5050:80"
    environment:
      PGADMIN_DEFAULT_EMAIL: ${PGADMIN_EMAIL}
      PGADMIN_DEFAULT_PASSWORD: ${PGADMIN_PASSWORD}
    volumes:
      - ./data/pgadmin:/var/lib/pgadmin
    depends_on:
      - postgres
    restart: unless-stopped

volumes:
  hf_models:    # Named volume — persists HuggingFace models across redeploys
```

## .env.example

```env
# PostgreSQL
POSTGRES_USER=raguser
POSTGRES_PASSWORD=changeme_strong_password
POSTGRES_DB=ragdb
DATABASE_URL=postgresql://raguser:changeme_strong_password@postgres:5432/ragdb

# pgAdmin
PGADMIN_EMAIL=admin@example.com
PGADMIN_PASSWORD=changeme_admin_password

# Qdrant — always use service name, never localhost
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=documents

# Gemini
GOOGLE_API_KEY=your_gemini_api_key_here

# HuggingFace
HF_HOME=/app/models
TRANSFORMERS_CACHE=/app/models
# HF_TOKEN=optional_for_private_models

# App
APP_ENV=production
LOG_LEVEL=info
```

## Notes

### Named volume vs bind mount for HF models

Use **named volume** (`hf_models:`) not bind mount (`./data/models:/app/models`).

Named volume reason: Docker manages it, survives `docker compose down`, 
does not require root permissions, and is preserved across image rebuilds.
With bind mount, a `docker compose down -v` will wipe your 1GB+ model download.

### Health check start_period

Backend needs `start_period: 60s` because:
- `BAAI/bge-small-en-v1.5` loads in ~15-20s cold
- `cross-encoder/ms-marco-MiniLM-L-6-v2` loads in ~10-15s
- Total cold start: 30-60s on 4GB VPS

Without this, Docker marks backend as unhealthy before it's ready
and Nginx returns 502.
