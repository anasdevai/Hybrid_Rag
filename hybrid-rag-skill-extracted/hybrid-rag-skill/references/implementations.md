# Extended Implementations Reference

## Table of Contents
1. Streaming Ingestion
2. BM25 Corpus Caching (Pickle)
3. HNSW ef Query Tuning
4. Async Batch Embedding
5. LangChain LCEL Chain Variant
6. Docker Compose — Full Stack
7. Metrics Instrumentation
8. Incremental / Delta Ingestion
9. Multi-category Filtering
10. Hallucination Guard

---

## 1. Streaming Ingestion

For very large APIs (millions of docs), stream pages and ingest in real-time
without holding all docs in memory.

```python
# ingestion/streaming_ingest.py
import asyncio, httpx, os
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from ingestion.chunker import chunk_documents
from embeddings.embedder import get_embedder

async def stream_ingest(vectorstore: QdrantVectorStore, category: str = None):
    embedder = get_embedder()
    page, page_size = 1, 100
    total = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            params = {"page": page, "limit": page_size}
            if category:
                params["category"] = category
            resp = await client.get(
                f"{os.getenv('API_BASE_URL')}/documents",
                headers={"Authorization": f"Bearer {os.getenv('API_KEY')}"},
                params=params,
            )
            data = resp.json()
            items = data.get("results", [])
            if not items:
                break

            docs = [
                Document(
                    page_content=item["content"],
                    metadata={
                        "source_id": item["id"],
                        "category": item.get("category", "general"),
                        "timestamp": item.get("updated_at", ""),
                        "tags": item.get("tags", []),
                        "url": item.get("url", ""),
                        "chunk_index": 0,
                    }
                )
                for item in items
            ]
            chunks = chunk_documents(docs)
            await vectorstore.aadd_documents(chunks)
            total += len(chunks)
            print(f"Page {page}: ingested {len(chunks)} chunks (total: {total})")

            if len(items) < page_size:
                break
            page += 1

    return total
```

---

## 2. BM25 Corpus Caching (Pickle)

Scrolling Qdrant for every query is slow at scale. Pickle the corpus on first build.

```python
# retrieval/bm25_cache.py
import pickle, os, time
from qdrant_client import QdrantClient
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document

CACHE_PATH = "/tmp/bm25_corpus.pkl"
CACHE_TTL = 3600  # rebuild every hour

def get_bm25_corpus(client: QdrantClient, collection: str):
    # Load from cache if fresh
    if os.path.exists(CACHE_PATH):
        mtime = os.path.getmtime(CACHE_PATH)
        if time.time() - mtime < CACHE_TTL:
            with open(CACHE_PATH, "rb") as f:
                return pickle.load(f)

    # Build fresh
    points, _ = client.scroll(
        collection_name=collection,
        limit=500_000,
        with_payload=True,
        with_vectors=False,
    )
    docs, tokenized = [], []
    for p in points:
        text = p.payload.get("page_content", "")
        docs.append(Document(
            page_content=text,
            metadata={**p.payload, "qdrant_id": p.id}
        ))
        tokenized.append(text.lower().split())

    bm25 = BM25Okapi(tokenized)
    payload = {"docs": docs, "bm25": bm25}
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(payload, f)
    return payload
```

---

## 3. HNSW ef Query Tuning

`ef` at query time controls the recall/speed tradeoff. Set it per-query.

```python
from qdrant_client.models import SearchParams

results = client.search(
    collection_name=collection,
    query_vector=query_vec,
    limit=50,
    search_params=SearchParams(hnsw_ef=128),  # higher = better recall, slower
    with_payload=True,
)
```

Recommended values:
- Development / small corpus: `hnsw_ef=64`
- Production / <1M docs: `hnsw_ef=128`
- High-recall / large corpus: `hnsw_ef=256`

---

## 4. Async Batch Embedding

When ingesting millions of chunks, parallelize embedding across CPU cores.

```python
# embeddings/async_batch.py
import asyncio
from sentence_transformers import SentenceTransformer
from langchain_core.documents import Document

async def embed_batch_async(
    docs: list[Document],
    model: SentenceTransformer,
    batch_size: int = 64,
) -> list[list[float]]:
    loop = asyncio.get_event_loop()
    texts = [d.page_content for d in docs]

    def _embed(batch):
        return model.encode(
            batch,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=False,
        ).tolist()

    all_vecs = []
    for i in range(0, len(texts), batch_size * 4):
        batch = texts[i:i + batch_size * 4]
        vecs = await loop.run_in_executor(None, _embed, batch)
        all_vecs.extend(vecs)
    return all_vecs
```

---

## 5. LangChain LCEL Chain Variant

Pure LCEL — composable, streamable, observable.

```python
# chain/lcel_chain.py
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

def make_lcel_chain(retriever, reranker, prompt):
    def retrieve_and_rerank(inputs):
        docs = retriever.invoke(inputs["question"])
        reranked = reranker.rerank(inputs["question"], docs)
        context = "\n\n".join(
            [f"[{i}] {d.page_content}" for i, d in enumerate(reranked)]
        )
        return {**inputs, "context": context, "docs": reranked}

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.2)

    chain = (
        RunnablePassthrough.assign(question=lambda x: x["question"])
        | RunnableLambda(retrieve_and_rerank)
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain

# Streaming usage:
# async for chunk in chain.astream({"question": "..."}):
#     print(chunk, end="", flush=True)
```

---

## 6. Docker Compose — Full Stack

```yaml
# docker-compose.yml
version: "3.9"
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru

  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - qdrant
      - redis
    command: uvicorn main:app --host 0.0.0.0 --port 8000

  ingest:
    build: .
    env_file:
      - .env
    depends_on:
      - qdrant
    command: python -m ingestion.ingest
    profiles:
      - ingest   # run with: docker compose --profile ingest up ingest
```

---

## 7. Metrics Instrumentation

Track Recall@5, latency, and hallucination proxy.

```python
# metrics/tracker.py
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class QueryMetrics:
    query: str
    latency_ms: float
    num_retrieved: int
    num_reranked: int
    top_rerank_score: float
    cache_hit: bool
    category_filter: Optional[str] = None

class MetricsTracker:
    def __init__(self):
        self.records: list[QueryMetrics] = []

    def record(self, **kwargs):
        self.records.append(QueryMetrics(**kwargs))

    def summary(self) -> dict:
        if not self.records:
            return {}
        lats = [r.latency_ms for r in self.records]
        return {
            "p50_latency_ms": sorted(lats)[len(lats)//2],
            "p95_latency_ms": sorted(lats)[int(len(lats)*0.95)],
            "avg_rerank_score": sum(r.top_rerank_score for r in self.records) / len(self.records),
            "cache_hit_rate": sum(1 for r in self.records if r.cache_hit) / len(self.records),
            "total_queries": len(self.records),
        }
```

---

## 8. Incremental / Delta Ingestion

Only ingest documents newer than last run. Uses timestamp metadata.

```python
# ingestion/delta_ingest.py
from datetime import datetime, timezone
import json, os

STATE_FILE = "/tmp/last_ingestion.json"

def get_last_timestamp() -> str:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f).get("last_ts", "")
    return ""

def save_timestamp(ts: str):
    with open(STATE_FILE, "w") as f:
        json.dump({"last_ts": ts}, f)

async def delta_ingest(vectorstore, fetcher, chunker):
    last_ts = get_last_timestamp()
    docs = await fetcher.fetch_since(last_ts)   # API must support `since=` param
    if not docs:
        print("No new documents.")
        return
    chunks = chunker(docs)
    await vectorstore.aadd_documents(chunks)
    save_timestamp(datetime.now(timezone.utc).isoformat())
    print(f"Delta ingested {len(chunks)} new chunks.")
```

---

## 9. Multi-category Filtering

Filter across multiple categories at once.

```python
from qdrant_client.models import Filter, FieldCondition, MatchAny

def build_multi_filter(categories: list[str]) -> Filter:
    return Filter(
        must=[
            FieldCondition(
                key="category",
                match=MatchAny(any=categories)
            )
        ]
    )
```

---

## 10. Hallucination Guard

Post-generation check: verify each citation exists in context.

```python
# chain/hallucination_guard.py
import re

def check_citations(answer: str, citations: list[dict]) -> dict:
    """Returns hallucination report."""
    cited_indices = set(int(m) for m in re.findall(r'\[(\d+)\]', answer))
    valid_indices = set(c["index"] for c in citations)
    hallucinated = cited_indices - valid_indices
    uncited = valid_indices - cited_indices
    return {
        "cited": sorted(cited_indices),
        "valid": sorted(valid_indices),
        "hallucinated_refs": sorted(hallucinated),   # refs in answer but not in context
        "uncited_sources": sorted(uncited),           # context chunks never referenced
        "clean": len(hallucinated) == 0,
    }
```
