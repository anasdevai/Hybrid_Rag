# Python Project Structure & Import Fixing

## Standard structure for RAG FastAPI project

```
backend/
├── main.py                    ← FastAPI app entry point
├── requirements.txt
├── Dockerfile
├── chain/
│   ├── __init__.py            ← REQUIRED in every package dir
│   └── rag_chain.py
├── retrieval/
│   ├── __init__.py
│   ├── hybrid_retriever.py
│   ├── reranker.py
│   ├── context_builder.py
│   ├── federated_retriever.py
│   └── query_router.py
├── routers/
│   ├── __init__.py
│   ├── webhook.py
│   ├── ingest.py
│   └── query.py
├── services/
│   ├── __init__.py
│   ├── embedder.py
│   └── qdrant_ops.py
├── models/
│   ├── __init__.py
│   └── schemas.py
└── database.py
```

## main.py — required header for Docker

Every `main.py` must have this at the very top:

```python
import sys
import os
# Ensure project root is on path — required when running inside Docker
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from fastapi import FastAPI

# Now imports work regardless of working directory
from chain.rag_chain import SmartRAGChain
from routers import webhook, ingest, query
```

## Import rules — absolute always

Inside Docker the working directory is `/app` (set by `WORKDIR /app` in Dockerfile).
All imports must be **absolute from `/app`**, never relative.

```python
# WRONG — relative imports fail in Docker
from .hybrid_retriever import HybridRetriever
from ..chain.rag_chain import SmartRAGChain
from . import utils

# CORRECT — absolute from project root
from retrieval.hybrid_retriever import HybridRetriever
from chain.rag_chain import SmartRAGChain
import utils
```

## How to find and fix all broken imports

```bash
# 1. Find all relative imports
grep -rn "^from \." --include="*.py" backend/

# 2. Find all imports that might be wrong
grep -rn "^from chain\|^from retrieval\|^from services\|^from routers" \
  --include="*.py" backend/

# 3. For each file, check what directory it's in and fix accordingly
# Example: backend/retrieval/reranker.py importing from same package
#   from .utils import helper  →  from retrieval.utils import helper

# 4. Add missing __init__.py
find backend/ -type d | while read dir; do
  if ! ls "$dir"/*.py > /dev/null 2>&1; then continue; fi
  if [ ! -f "$dir/__init__.py" ]; then
    touch "$dir/__init__.py"
    echo "Created: $dir/__init__.py"
  fi
done
```

## Common import errors and fixes

### `ModuleNotFoundError: No module named 'chain'`
```
Cause: sys.path doesn't include /app
Fix:   Add sys.path.insert(0, ...) to main.py
```

### `ImportError: attempted relative import with no known parent package`
```
Cause: from .module import X in a file run as __main__
Fix:   Change to absolute import: from package.module import X
```

### `ModuleNotFoundError: No module named 'retrieval.hybrid_retriever'`
```
Cause: Missing __init__.py in retrieval/ directory
Fix:   touch backend/retrieval/__init__.py
```

### `cannot import name 'X' from 'Y'`
```
Cause: Wrong module path or circular import
Fix:   Check actual file location and class/function name
       Check for circular imports (A imports B, B imports A)
```

## requirements.txt — minimum for this RAG stack

```txt
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.9       # for file uploads

# LangChain
langchain>=0.2.0
langchain-google-genai>=1.0.0
langchain-qdrant>=0.1.0
langchain-core>=0.2.0

# Vector + Search
qdrant-client>=1.9.0
rank-bm25>=0.2.2

# HuggingFace
sentence-transformers>=3.0.0
torch>=2.2.0                  # CPU only — no CUDA on Hetzner 4GB
transformers>=4.40.0

# Database
sqlalchemy>=2.0.0
asyncpg>=0.29.0
psycopg2-binary>=2.9.0
alembic>=1.13.0

# Document parsing (for /ingest)
pypdf>=4.0.0
python-docx>=1.1.0
langchain-text-splitters>=0.2.0

# Utils
python-dotenv>=1.0.0
pydantic>=2.7.0
pydantic-settings>=2.2.0
httpx>=0.27.0
```

**IMPORTANT:** Do NOT add `torch` with CUDA — Hetzner 4GB VPS has no GPU.
CPU-only torch is installed automatically by sentence-transformers.
If torch tries to download CUDA version, add to Dockerfile:
```dockerfile
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r requirements.txt
```
