# 4GB RAM Optimization for RAG on Hetzner VPS

## Memory budget

| Service | Idle RAM | Peak RAM |
|---------|----------|----------|
| OS + Docker | ~400 MB | ~400 MB |
| Qdrant | ~200 MB | ~500 MB |
| Postgres | ~100 MB | ~200 MB |
| pgAdmin | ~150 MB | ~150 MB |
| Nginx | ~10 MB | ~10 MB |
| **Backend (HF models)** | **~900 MB** | **~1.5 GB** |
| **Total** | **~1.8 GB** | **~2.8 GB** |

4GB VPS has ~200-500 MB headroom. Stay within budget.

## Model choices (critical for 4GB)

```python
# CORRECT — small models for 4GB VPS
embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")    # ~130 MB
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")  # ~90 MB

# WRONG — too large for 4GB VPS
embedder = SentenceTransformer("BAAI/bge-large-en-v1.5")    # ~1.3 GB → OOM
reranker = CrossEncoder("cross-encoder/ms-marco-TinyBERT-L-2-v2")  # OK but less accurate
```

## Load models ONCE — never per request

```python
# main.py — correct pattern
from contextlib import asynccontextmanager
from fastapi import FastAPI

_embedder = None
_reranker = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _embedder, _reranker
    print("Loading HF models...")
    from sentence_transformers import SentenceTransformer, CrossEncoder
    _embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    print("Models loaded. Ready.")
    yield
    # Cleanup on shutdown
    _embedder = None
    _reranker = None

app = FastAPI(lifespan=lifespan)

def get_embedder(): return _embedder
def get_reranker(): return _reranker
```

## uvicorn workers — 1 only

```dockerfile
# WRONG — 2 workers = 2x model memory = OOM
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# CORRECT — 1 worker on 4GB VPS
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

## Gemini thinking mode — disable it

Gemini 2.5 Flash has thinking mode ON by default — adds 10-20s latency and token cost.

```python
def get_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=temperature,
        max_output_tokens=2048,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        thinking_budget=0,    # CRITICAL — disables thinking, 30s → 4s
    )
```

## Docker memory limits (optional but recommended)

Add to `docker-compose.yml` to prevent any single service from OOMing the VPS:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G        # Hard cap — prevents OOM killing other services
        reservations:
          memory: 800M

  qdrant:
    deploy:
      resources:
        limits:
          memory: 600M

  postgres:
    deploy:
      resources:
        limits:
          memory: 256M
```

## Swap space (safety net for 4GB VPS)

If not already set, add 2GB swap as safety net:

```bash
# Check existing swap
free -h

# Add 2GB swap if none
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Reduce swappiness (use RAM first)
echo 'vm.swappiness=10' >> /etc/sysctl.conf
sysctl -p
```

Swap prevents total OOM crash but is slow — it's a safety net, not a performance tool.

## Monitor RAM in production

```bash
# Real-time Docker memory usage
docker stats --no-stream

# Check if any OOM kills happened
dmesg | grep -i "oom\|killed process" | tail -10

# Overall system memory
free -h

# Which process uses most RAM
ps aux --sort=-%mem | head -10
```
