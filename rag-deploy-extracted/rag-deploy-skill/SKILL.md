---
name: rag-deploy
description: >
  Full production deployment skill for Hybrid RAG FastAPI projects on a Linux VPS (Hetzner/Ubuntu).
  Use this skill whenever the user wants to deploy, redeploy, update, or fix deployment of any 
  RAG chatbot project involving FastAPI + React + Qdrant + PostgreSQL + HuggingFace models + Nginx.
  Triggers on: "deploy my RAG project", "set up server", "Docker Compose deploy", "CI/CD pipeline",
  "deploy to Hetzner", "production deployment", "deploy FastAPI chatbot", "server setup".
  This skill handles the FULL pipeline: file audit → structure fix → import path fix → 
  Dockerfile → Docker Compose → Nginx → CI/CD → smoke tests. Always use this skill for 
  any multi-service RAG deployment task, even if the user only mentions one part of it.
---

# RAG Project — Full Production Deployment Skill

## What this skill does

End-to-end deployment of a Hybrid RAG chatbot to a Ubuntu VPS:

1. **Audit** — Read all project files, map actual structure
2. **Fix** — Correct import paths, missing `__init__.py`, broken references  
3. **Dockerize** — Write optimized Dockerfiles for backend + frontend
4. **Compose** — Write full `docker-compose.yml` (no Redis by default)
5. **Nginx** — Reverse proxy config with correct timeouts for RAG
6. **CI/CD** — Git-based one-command deploy script
7. **Test** — Smoke test all endpoints after deploy

---

## Step 0 — Read the right reference files first

Before doing ANYTHING, read these based on the task:

| Task | Read |
|------|------|
| First-time deploy | `references/docker.md` + `references/nginx.md` |
| Import/path errors | `references/python-structure.md` |
| CI/CD setup | `references/cicd.md` |
| Post-deploy testing | `references/testing.md` |
| Server is 4GB RAM | `references/ram-optimization.md` |

---

## Step 1 — Audit the project

Run this to map all Python files and their imports:

```bash
# Map full project structure
find . -type f -name "*.py" | head -60
find . -type f -name "*.py" -exec grep -l "^from\|^import" {} \;

# Find all relative imports that might break inside Docker
grep -rn "^from \.\|^from chain\|^from retrieval\|^from services" --include="*.py" .

# Check for missing __init__.py
find . -type d | while read d; do
  [ ! -f "$d/__init__.py" ] && echo "MISSING __init__.py: $d"
done

# Check requirements.txt exists
ls -la requirements.txt pyproject.toml setup.py 2>/dev/null || echo "NO requirements file found"

# Check React frontend
ls frontend/package.json 2>/dev/null || ls package.json 2>/dev/null || echo "No frontend found"
```

**Record what you find:**
- Root package name (e.g. `chain/`, `retrieval/`, `services/`)
- Entry point file (e.g. `main.py`, `app.py`, `api/main.py`)
- Frontend location (`frontend/`, `client/`, root)
- Missing `__init__.py` files
- Broken import paths

---

## Step 2 — Fix project structure

### 2a. Add missing `__init__.py` files

```bash
# Add to every Python package directory
for dir in chain retrieval services routers api utils models; do
  [ -d "$dir" ] && touch "$dir/__init__.py" && echo "Created $dir/__init__.py"
done
```

### 2b. Fix import paths

All imports must be **absolute from project root** inside Docker.

Common patterns to fix:

```python
# WRONG — relative imports break in Docker
from .hybrid_retriever import HybridRetriever
from ..utils import helper

# CORRECT — absolute from project root
from retrieval.hybrid_retriever import HybridRetriever  
from utils.helper import helper
```

Run a find-replace across all files:
```bash
# Find all problematic relative imports
grep -rn "^from \." --include="*.py" . 

# Fix pattern: "from .module" → "from package.module"
# Do this manually per file based on actual directory structure
```

### 2c. Verify entry point

The `main.py` (or equivalent) must have:
```python
# At the very top — needed for Docker WORKDIR /app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

---

## Step 3 — Write Dockerfile (backend)

See `references/docker.md` for full templates. Key rules for RAG projects:

- Use `python:3.11-slim` base
- Install system deps for HuggingFace: `build-essential libgomp1`  
- Copy `requirements.txt` first (layer cache)
- Set `HF_HOME=/app/models` and `TRANSFORMERS_CACHE=/app/models`
- Use `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]`
- **1 worker only** on 4GB RAM — multiple workers will OOM with HF models

---

## Step 4 — Write docker-compose.yml

See `references/docker.md` for full compose template.

**Service order:** nginx → backend → qdrant + postgres (no Redis)

**Critical:** HF models must use a **named volume** (not bind mount) so they survive rebuilds:
```yaml
volumes:
  hf_models:   # defined at bottom — persists across redeploys
```

---

## Step 5 — Nginx config

See `references/nginx.md` for full config. 

**RAG-specific timeouts (critical):**
- `/api/` → `proxy_read_timeout 120s` (Gemini + reranker is slow)
- `/webhook/` → `proxy_read_timeout 30s` (BackgroundTasks return 202 fast)
- `/ingest/` → `proxy_read_timeout 30s` (BackgroundTasks return 202 fast)

---

## Step 6 — CI/CD pipeline

See `references/cicd.md` for full deploy script.

One-command deploy from local machine:
```bash
alias deploy="git push origin main && ssh root@SERVER_IP 'cd /opt/PROJECT && ./deploy.sh'"
```

`deploy.sh` only rebuilds backend — never restarts Qdrant or Postgres (data safety).

---

## Step 7 — First-time server setup

```bash
ssh root@SERVER_IP

# Install Docker
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin git

# Clone project
cd /opt && git clone https://github.com/USER/REPO.git PROJECT_NAME
cd PROJECT_NAME

# Create .env from example
cp .env.example .env
nano .env   # fill in real values

# Create data directories
mkdir -p data/qdrant data/postgres data/pgadmin

# First launch (builds everything)
docker compose up -d --build

# Watch backend logs for model loading
docker compose logs -f backend
```

---

## Step 8 — Smoke tests

See `references/testing.md` for full test suite. Run after every deploy:

```bash
# Quick health check
curl -f http://SERVER_IP/api/health || echo "BACKEND DOWN"

# Test query endpoint  
curl -X POST http://SERVER_IP/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "test", "collection": "SOPs"}' | python3 -m json.tool

# Check all containers running
docker compose ps

# Check no OOM kills
dmesg | grep -i "oom\|killed" | tail -5
```

---

## Common errors and fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'chain'` | Import path wrong | Add `sys.path.insert` to main.py |
| `CUDA out of memory` | Loading model per request | Use lifespan, load once |
| `502 Bad Gateway` | Backend crashed on startup | `docker compose logs backend` |
| `Qdrant connection refused` | Wrong URL in .env | Use `http://qdrant:6333` not localhost |
| `HF model re-downloads every restart` | Bind mount vs named volume | Use named volume `hf_models` |
| Backend takes 30s+ to respond | Thinking mode on Gemini | Add `thinking_budget=0` to LLM init |
| `pg_hba.conf` auth error | Postgres env vars wrong | Check `POSTGRES_USER` matches `DATABASE_URL` |

---

## File output checklist

When deploying, produce ALL of these files:

- [ ] `backend/Dockerfile`
- [ ] `docker-compose.yml`  
- [ ] `.env.example`
- [ ] `nginx/nginx.conf`
- [ ] `deploy.sh`
- [ ] `scripts/smoke_test.sh`
- [ ] `.dockerignore`
- [ ] `.gitignore` (with `.env` excluded)
- [ ] Any fixed Python files (broken imports)
- [ ] Any missing `__init__.py` files

---

## Reference files in this skill

- `references/docker.md` — Full Dockerfile + docker-compose templates
- `references/nginx.md` — Full Nginx config with RAG timeouts
- `references/cicd.md` — deploy.sh + GitHub Actions workflow
- `references/python-structure.md` — Import fixing guide
- `references/testing.md` — Smoke test scripts
- `references/ram-optimization.md` — 4GB RAM constraints and fixes
