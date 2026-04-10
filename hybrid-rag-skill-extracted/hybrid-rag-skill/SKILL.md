---
name: hybrid-rag-chatbot
description: >
  Complete production guide for building a Hybrid RAG (Retrieval-Augmented Generation) chatbot
  using LangChain, Qdrant, and Gemini/OpenAI. Covers the full pipeline: fetching data from
  external APIs (with separate endpoints per entity type), chunking with metadata, embedding
  with bge-small-en-v1.5, storing in SEPARATE Qdrant collections per entity type (SOPs,
  Deviations, CAPAs, Decisions, Audit Findings), federated hybrid retrieval (dense + BM25)
  run in parallel across all collections, cross-encoder reranking per section, structured
  multi-section AI response generation, and a JSON response builder with per-entity citations.

  ALWAYS use this skill when the user asks about: RAG pipelines, hybrid search, Qdrant setup,
  semantic search with reranking, LangChain RAG chains, ingestion pipelines, vector stores,
  BM25 + dense retrieval, cross-encoder reranking, multi-collection Qdrant, federated search,
  structured JSON RAG responses, or building a chatbot over multi-entity regulatory data.
  Trigger even if the user only mentions parts of the pipeline (e.g. "separate Qdrant collections
  per entity", "how do I ingest deviations and SOPs into different collections", or "structured
  output with sections for CAPAs and Decisions").
---

# Hybrid RAG Chatbot — Production Skill

Full implementation guide. Follow sections in order. Each section has exact code, parameters,
and rationale. Read the reference file for a section only when directed.

---

## 0. Stack & Parameters (memorize these)

| Component | Choice | Key param |
|---|---|---|
| Orchestration | LangChain | `langchain>=0.2`, `langchain-community` |
| Vector store | Qdrant (multi-collection) | cosine, HNSW `m=16 ef=100` |
| Embedding | `BAAI/bge-small-en-v1.5` | 384 dims, normalize=True |
| Sparse retrieval | BM25 via `rank_bm25` | Top-50 per collection |
| Dense retrieval | Qdrant dense | Top-50 per collection |
| Federated Search | `asyncio.gather()` | All collections queried in parallel |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Applied per section (SOP, DEV, CAPA...) |
| LLM | Gemini 2.5 Flash (or GPT-4o-mini) | temp=0.2, max_tokens=2048 |
| Cache | Redis | TTL=3600s, keyed by query+filters |
| Chunk size | 500 tokens | overlap=50 |
| Fusion weights | 0.7 dense + 0.3 BM25 | tunable per collection |
| Max context | ~3000 tokens per section | merge all sections before LLM call |
| Latency target | <5s total (parallel fetch) | |
| Recall target | ≥90% @ Top-5 per section | |
| Collections | `docs_sops`, `docs_deviations`, `docs_capas`, `docs_decisions`, `docs_audits` | one per entity |

**For detailed code of any section → read** `references/implementations.md`

---

## 1. Project Setup

### Install dependencies

```bash
pip install langchain langchain-community langchain-google-genai \
    qdrant-client sentence-transformers rank-bm25 \
    redis fastapi uvicorn httpx python-dotenv \
    langchain-huggingface
```

### `.env` file

```env
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_key          # leave blank for local
GOOGLE_API_KEY=your_gemini_key
REDIS_URL=redis://localhost:6379
API_BASE_URL=https://your-data-api.com
API_KEY=your_data_api_key

# Multi-Collection config — one per entity type
COLLECTION_SOPS=docs_sops
COLLECTION_DEVIATIONS=docs_deviations
COLLECTION_CAPAS=docs_capas
COLLECTION_DECISIONS=docs_decisions
COLLECTION_AUDITS=docs_audits
```

> **Why separate collections?** Each entity type (SOP, Deviation, CAPA...) arrives from a
> different API endpoint with different field names and semantics. Keeping them in separate
> collections means:
> - You always know the category of a retrieved chunk without reading metadata tags.
> - You can tune HNSW, chunk size, and BM25 weights independently per entity type.
> - The structured response sections (`## SOPs`, `## Deviations`, etc.) map 1:1 to collections.

### Run Qdrant locally

```bash
docker run -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

---

## 2. Data Ingestion from API (Multi-Collection)

**Goal**: Fetch each entity type from its own API endpoint and store it in its own Qdrant collection.

### Entity-to-Endpoint Mapping

| Entity Type | API Endpoint | Qdrant Collection | Key Fields to Preserve |
|---|---|---|---|
| SOP | `GET /sops` | `docs_sops` | `sop_number`, `title`, `department`, `content_json` |
| Deviation | `GET /deviations` | `docs_deviations` | `deviation_number`, `title`, `description_text`, `root_cause_text`, `impact_level` |
| CAPA | `GET /capas` | `docs_capas` | `capa_number`, `title`, `action_text`, `external_status` |
| Decision | `GET /decisions` | `docs_decisions` | `decision_number`, `title`, `decision_statement`, `rationale_text` |
| Audit Finding | `GET /audit_findings` | `docs_audits` | `finding_number`, `finding_text`, `acceptance_status` |

### Metadata schema per entity (mandatory on every chunk)

Every chunk stored in Qdrant **must** carry these fields in its payload:

```python
# Mandatory for ALL entity types
{
    "doc_type":    str,   # "sop" | "deviation" | "capa" | "decision" | "audit"
    "ref_number":  str,   # e.g. "SOP-IT-001", "DEV-IT-001"
    "title":       str,
    "chunk_id":    str,   # e.g. "SOP-IT-001_chunk_0"
    "chunk_index": int,
    "status":      str,   # "effective" | "open" | "closed" | "accepted"
}

# Additional fields per type (store what you have, ignore the rest)
# SOP extras:       "department", "sop_number"
# Deviation extras: "impact_level", "root_cause_text"
# CAPA extras:      "capa_number"
# Decision extras:  "rationale_text"
# Audit extras:     "finding_number", "acceptance_status"
```

### SOP content_json flattening rule

SOP content arrives as a nested JSON (TipTap/ProseMirror format). Before chunking:
1. Walk all `content` nodes recursively.
2. Concatenate `text` values, preserving heading levels with `##` markers.
3. The resulting plain text is what gets embedded and stored as `page_content`.

### Multi-entity fetcher pattern

```python
# ingestion/multi_fetcher.py — conceptual pattern
# One async function per entity type, all called in parallel via asyncio.gather()

async def fetch_sops(client)     -> list[Document]: ...  # calls GET /sops
async def fetch_deviations(client) -> list[Document]: ...  # calls GET /deviations
async def fetch_capas(client)    -> list[Document]: ...  # calls GET /capas
async def fetch_decisions(client)-> list[Document]: ...  # calls GET /decisions
async def fetch_audits(client)   -> list[Document]: ...  # calls GET /audit_findings

async def fetch_all_entities():
    async with httpx.AsyncClient(timeout=30) as client:
        results = await asyncio.gather(
            fetch_sops(client),
            fetch_deviations(client),
            fetch_capas(client),
            fetch_decisions(client),
            fetch_audits(client),
        )
    return {
        "sops":       results[0],
        "deviations": results[1],
        "capas":      results[2],
        "decisions":  results[3],
        "audits":     results[4],
    }
```

### Ingestion rule: one collection per entity type

```python
# storage/multi_ingest.py — conceptual pattern
# After fetching + chunking, upsert each group into its own collection:

for entity_type, collection_name in [
    ("sops",       os.getenv("COLLECTION_SOPS")),
    ("deviations", os.getenv("COLLECTION_DEVIATIONS")),
    ("capas",      os.getenv("COLLECTION_CAPAS")),
    ("decisions",  os.getenv("COLLECTION_DECISIONS")),
    ("audits",     os.getenv("COLLECTION_AUDITS")),
]:
    chunks = chunked_entities[entity_type]     # already chunked + metadata attached
    create_collection(client, collection_name)  # idempotent
    await QdrantVectorStore.afrom_documents(
        documents=chunks,
        embedding=embedder,
        collection_name=collection_name,
        ...                                   # url, api_key from env
    )
```

→ **Streaming ingestion**: see `references/implementations.md § Streaming Ingestion`

---

## 3. Chunking

**Always use `RecursiveCharacterTextSplitter` with token counting.**

```python
# ingestion/chunker.py
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import copy

def chunk_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,               # swap for tiktoken if needed
        separators=["\n\n", "\n", ". ", " ", ""],
        keep_separator=True,
    )
    chunked = []
    for doc in docs:
        splits = splitter.split_documents([doc])
        for i, chunk in enumerate(splits):
            chunk.metadata = copy.deepcopy(doc.metadata)
            chunk.metadata["chunk_index"] = i
            chunk.metadata["chunk_id"] = f"{doc.metadata['source_id']}_chunk_{i}"
        chunked.extend(splits)
    return chunked
```

---

## 4. Embedding + Qdrant Storage

### Embedding model setup

```python
# embeddings/embedder.py
from langchain_huggingface import HuggingFaceEmbeddings

def get_embedder() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
        model_kwargs={"device": "cpu"},           # "cuda" if GPU available
        encode_kwargs={
            "normalize_embeddings": True,         # mandatory for cosine
            "batch_size": 64,
        },
    )
```

### Create Qdrant collection (run once)

```python
# storage/qdrant_setup.py
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, HnswConfigDiff,
    PayloadSchemaType
)
import os

def create_collection(client: QdrantClient, name: str):
    client.recreate_collection(
        collection_name=name,
        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE,
        ),
        hnsw_config=HnswConfigDiff(
            m=16,                   # connections per node — higher = better recall
            ef_construct=100,       # build-time search width — higher = better index
            full_scan_threshold=10_000,
        ),
        on_disk_payload=True,       # large payloads on disk to save RAM
    )
    # Payload indexes for metadata filtering
    for field, schema in [
        ("category", PayloadSchemaType.KEYWORD),
        ("source_id", PayloadSchemaType.KEYWORD),
        ("timestamp", PayloadSchemaType.DATETIME),
        ("tags",      PayloadSchemaType.KEYWORD),
    ]:
        client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=schema,
        )
    print(f"Collection '{name}' created with payload indexes.")
```

### Ingest chunks into Qdrant via LangChain

```python
# storage/ingest.py
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from embeddings.embedder import get_embedder
import os, asyncio
from ingestion.api_fetcher import APIDataFetcher
from ingestion.chunker import chunk_documents
from storage.qdrant_setup import create_collection

async def run_ingestion(category: str = None):
    client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY") or None,
    )
    collection = os.getenv("COLLECTION_NAME")
    create_collection(client, collection)           # idempotent recreate

    fetcher = APIDataFetcher()
    raw_docs = await fetcher.fetch_all(category=category)
    print(f"Fetched {len(raw_docs)} docs from API")

    chunks = chunk_documents(raw_docs)
    print(f"Produced {len(chunks)} chunks")

    embedder = get_embedder()
    # Batch upsert — LangChain handles batching internally
    vectorstore = await QdrantVectorStore.afrom_documents(
        documents=chunks,
        embedding=embedder,
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY") or None,
        collection_name=collection,
        batch_size=64,
    )
    print(f"Ingested {len(chunks)} chunks into Qdrant")
    return vectorstore

if __name__ == "__main__":
    asyncio.run(run_ingestion())
```

---

## 5. Federated Hybrid Retrieval (Dense + BM25 across Multiple Collections)

**The core change from single-collection RAG: run HybridRetriever independently against
each collection in parallel, then pass the categorized results to the structured response builder.**

### 5a. Per-Collection HybridRetriever (unchanged logic, new pattern)

The `HybridRetriever` class remains the same (Dense + BM25 fusion), **but it is instantiated
once per collection at startup**:

```python
# retrieval/federated_retriever.py — conceptual pattern

# One retriever per collection, all sharing the same embedder and reranker
retrievers = {
    "sops":       HybridRetriever(vectorstore=vs_sops,       collection_name="docs_sops"),
    "deviations": HybridRetriever(vectorstore=vs_deviations, collection_name="docs_deviations"),
    "capas":      HybridRetriever(vectorstore=vs_capas,      collection_name="docs_capas"),
    "decisions":  HybridRetriever(vectorstore=vs_decisions,  collection_name="docs_decisions"),
    "audits":     HybridRetriever(vectorstore=vs_audits,     collection_name="docs_audits"),
}
```

### 5b. Parallel Federated Search

At query time, all retrievers run **simultaneously** via `asyncio.gather()`:

```python
# retrieval/federated_retriever.py — conceptual pattern

async def federated_search(query: str) -> dict[str, list[Document]]:
    """
    Returns a dict of section → list of retrieved documents.
    Keys map directly to the response JSON sections.
    """
    import asyncio

    results = await asyncio.gather(
        asyncio.to_thread(retrievers["sops"].invoke,       query),
        asyncio.to_thread(retrievers["deviations"].invoke, query),
        asyncio.to_thread(retrievers["capas"].invoke,      query),
        asyncio.to_thread(retrievers["decisions"].invoke,  query),
        asyncio.to_thread(retrievers["audits"].invoke,     query),
    )

    return {
        "sops":       results[0],
        "deviations": results[1],
        "capas":      results[2],
        "decisions":  results[3],
        "audits":     results[4],
    }
```

### 5c. Per-Section Reranking

After federated search, rerank **within each section independently**. Do not mix sections
before reranking — the cross-encoder needs topically consistent pairs.

```python
# retrieval/federated_retriever.py — conceptual pattern

reranked = {}
for section, docs in raw_results.items():
    # Each section gets its own top_n — tune per entity type
    top_n = 3 if section in ("capas", "decisions", "audits") else 5
    reranked[section] = reranker.rerank(query, docs, top_n=top_n)
```

### 5d. HybridRetriever internal logic (Dense + BM25 fusion — unchanged)

The `HybridRetriever` used for each collection follows the same Dense+BM25 fusion:

```python
# retrieval/hybrid_retriever.py
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from rank_bm25 import BM25Okapi
from typing import Optional
import numpy as np

class HybridRetriever(BaseRetriever):
    vectorstore: QdrantVectorStore
    client: QdrantClient
    collection_name: str
    dense_top_k: int = 50
    bm25_top_k: int = 50
    dense_weight: float = 0.7
    bm25_weight: float = 0.3
    final_top_k: int = 20          # fed to reranker

    class Config:
        arbitrary_types_allowed = True

    def _get_bm25_corpus(self) -> tuple[list[Document], BM25Okapi]:
        """Scroll all payloads to build BM25 corpus. Cache in production."""
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            limit=100_000,
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
        return docs, BM25Okapi(tokenized)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        # Dense retrieval
        dense_results = self.vectorstore.similarity_search_with_score(
            query=query, k=self.dense_top_k
        )
        # BM25 retrieval
        corpus_docs, bm25 = self._get_bm25_corpus()
        bm25_scores = bm25.get_scores(query.lower().split())
        top_bm25_idx = np.argsort(bm25_scores)[::-1][:self.bm25_top_k]
        bm25_results = [
            (corpus_docs[i], float(bm25_scores[i])) for i in top_bm25_idx
        ]
        # Score fusion (normalize + weighted sum)
        def norm(scores):
            s = np.array(scores)
            mn, mx = s.min(), s.max()
            return (s - mn) / (mx - mn + 1e-9)

        combined: dict[str, dict] = {}
        d_scores = norm([s for _, s in dense_results])
        for (doc, _), ns in zip(dense_results, d_scores):
            cid = doc.metadata.get("chunk_id", doc.page_content[:40])
            combined[cid] = {"doc": doc, "score": self.dense_weight * ns}

        b_scores = norm([s for _, s in bm25_results])
        for (doc, _), ns in zip(bm25_results, b_scores):
            cid = doc.metadata.get("chunk_id", doc.page_content[:40])
            if cid in combined:
                combined[cid]["score"] += self.bm25_weight * ns
            else:
                combined[cid] = {"doc": doc, "score": self.bm25_weight * ns}

        ranked = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
        return [r["doc"] for r in ranked[:self.final_top_k]]
```

---

## 6. Reranking

```python
# retrieval/reranker.py
from sentence_transformers import CrossEncoder
from langchain_core.documents import Document

class CrossEncoderReranker:
    def __init__(self, top_n: int = 8):
        self.model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            max_length=512,
        )
        self.top_n = top_n

    def rerank(self, query: str, docs: list[Document]) -> list[Document]:
        if not docs:
            return []
        pairs = [(query, doc.page_content) for doc in docs]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        top = ranked[:self.top_n]
        for doc, score in top:
            doc.metadata["rerank_score"] = float(score)
        return [doc for doc, _ in top]
```

---

## 7. Context Builder + Citation System

```python
# retrieval/context_builder.py
from langchain_core.documents import Document

MAX_CONTEXT_CHARS = 12_000  # ≈ 3000 tokens

def build_context(docs: list[Document]) -> tuple[str, list[dict]]:
    """Returns (context_string, citation_map)"""
    context_parts = []
    citations = []
    total = 0

    for i, doc in enumerate(docs):
        snippet = doc.page_content.strip()
        if total + len(snippet) > MAX_CONTEXT_CHARS:
            break
        context_parts.append(f"[{i}] {snippet}")
        citations.append({
            "index": i,
            "source_id": doc.metadata.get("source_id", ""),
            "chunk_id": doc.metadata.get("chunk_id", ""),
            "category": doc.metadata.get("category", ""),
            "url": doc.metadata.get("url", ""),
            "rerank_score": doc.metadata.get("rerank_score", 0.0),
        })
        total += len(snippet)

    return "\n\n".join(context_parts), citations
```

---

## 8. Section-Aware LLM Chain + Structured Response Builder

### 8a. Section-Aware Prompt Engineering

The prompt must instruct Gemini to:
1. Organize the answer into fixed Markdown sections (`## SOPs`, `## Deviations`, `## CAPAs`, `## Decisions`).
2. Use citation tags in the format `[SOP-N]`, `[DEV-N]`, `[CAPA-N]`, `[DEC-N]`.
3. Respond in the **same language** as the user query (auto-detect).
4. Never invent information not present in the supplied context.

```python
# chain/rag_chain.py — section-aware prompt

SYSTEM_PROMPT = """
You are a regulatory compliance assistant. You answer ONLY from the provided context.
You MUST structure your answer into these exact sections using Markdown headers:

## SOPs
## Deviations
## CAPAs
## Decisions

Rules:
- Each factual claim must be followed by an inline citation in format [SOP-N], [DEV-N], [CAPA-N], [DEC-N].
- If a section has no relevant context, write: "No relevant [entity type] found."
- Do NOT use prior knowledge. Do NOT hallucinate.
- Respond in the SAME language as the user's question.
"""

USER_PROMPT = """
SOPs Context:
{context_sops}

Deviations Context:
{context_deviations}

CAPAs Context:
{context_capas}

Decisions Context:
{context_decisions}

Question: {question}

Respond using the structured format with citations:
"""
```

### 8b. Response Schema (matches EXAMPLE_RESPONSE.md)

The final API response must match this JSON structure exactly:

```json
{
  "answer": "## SOPs\n... [SOP-0] ...\n\n## Deviations\n...",
  "language": "en",
  "sections": {
    "sops":       "Plain text of SOPs section only",
    "deviations": "Plain text of Deviations section only",
    "capas":      "Plain text of CAPAs section only",
    "decisions":  "Plain text of Decisions section only"
  },
  "citations": [
    {
      "tag":          "[SOP-0]",
      "ref":          "SOP-IT-001",
      "title":        "...",
      "chunk_id":     "SOP-IT-001_chunk_0",
      "rerank_score": 9.41,
      "section":      "SOPs"
    }
  ],
  "citation_check": {
    "found":        ["[SOP-0]", "[DEV-0]"],
    "valid":        ["[SOP-0]", "[DEV-0]"],
    "hallucinated": [],
    "clean":        true
  },
  "retrieval_stats": {
    "sop_chunks_retrieved":       5,
    "deviation_chunks_retrieved": 4,
    "capa_chunks_retrieved":      2,
    "decision_chunks_retrieved":  1,
    "retrieval_latency_ms":       847.3
  },
  "cached": false
}
```

### 8c. Response Builder Logic (conceptual)

After the LLM returns its answer string:

1. **Parse sections**: Split the answer on `## SOPs`, `## Deviations`, etc. to extract per-section text.
2. **Assign citation tags**: Map `[SOP-N]` → `citations[N]` by iterating through all retrieved chunks per section.
3. **Citation check**: Verify every tag in the answer string appears in your citations list → populate `hallucinated`.
4. **Build `retrieval_stats`**: Count retrieved chunks per collection and measure wall-clock latency.
5. **Language detection**: Use a simple library like `langdetect` on the query string to fill the `language` field.

```python
# chain/rag_chain.py — conceptual HybridRAGChain.invoke() output

class HybridRAGChain:
    def invoke(self, query: str) -> dict:
        start_time = time.time()

        # 1. Federated hybrid search (parallel, all collections)
        raw = await federated_search(query)

        # 2. Per-section reranking
        reranked = {section: reranker.rerank(query, docs)
                    for section, docs in raw.items()}

        # 3. Build per-section context strings + tag→chunk citation maps
        context_sops,       cits_sops       = build_section_context(reranked["sops"],       "SOP")
        context_deviations, cits_deviations = build_section_context(reranked["deviations"], "DEV")
        context_capas,      cits_capas      = build_section_context(reranked["capas"],      "CAPA")
        context_decisions,  cits_decisions  = build_section_context(reranked["decisions"],  "DEC")

        # 4. LLM call with section-aware prompt
        answer = llm.invoke(prompt.format(
            context_sops=context_sops,
            context_deviations=context_deviations,
            context_capas=context_capas,
            context_decisions=context_decisions,
            question=query,
        ))

        # 5. Build final structured response dict
        all_citations = cits_sops + cits_deviations + cits_capas + cits_decisions
        sections      = parse_answer_sections(answer)
        citation_check = verify_citations(answer, all_citations)
        latency        = (time.time() - start_time) * 1000

        return build_response(
            answer, sections, all_citations, citation_check, raw, latency
        )
```

---

## 9. Redis Caching Layer

```python
# cache/redis_cache.py
import redis, json, hashlib, os
from typing import Optional

class RAGCache:
    def __init__(self, ttl: int = 3600):
        self.r = redis.from_url(os.getenv("REDIS_URL"))
        self.ttl = ttl

    def _key(self, query: str, category: Optional[str]) -> str:
        raw = f"{query}::{category or ''}"
        return "rag:" + hashlib.sha256(raw.encode()).hexdigest()

    def get(self, query: str, category: Optional[str]) -> Optional[dict]:
        val = self.r.get(self._key(query, category))
        return json.loads(val) if val else None

    def set(self, query: str, category: Optional[str], result: dict):
        self.r.setex(
            self._key(query, category),
            self.ttl,
            json.dumps(result),
        )
```

---

## 10. FastAPI Endpoint

```python
# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from embeddings.embedder import get_embedder
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.reranker import CrossEncoderReranker
from chain.rag_chain import HybridRAGChain
from cache.redis_cache import RAGCache
import os

app = FastAPI(title="Hybrid RAG API")

# Startup: initialize shared resources
@app.on_event("startup")
async def startup():
    app.state.cache = RAGCache()
    client = QdrantClient(url=os.getenv("QDRANT_URL"))
    embedder = get_embedder()
    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=os.getenv("COLLECTION_NAME"),
        embedding=embedder,
    )
    retriever = HybridRetriever(
        vectorstore=vectorstore,
        client=client,
        collection_name=os.getenv("COLLECTION_NAME"),
    )
    reranker = CrossEncoderReranker(top_n=8)
    app.state.rag = HybridRAGChain(retriever, reranker)

class QueryRequest(BaseModel):
    query: str
    category: Optional[str] = None

class QueryResponse(BaseModel):
    answer: str
    citations: list[dict]
    cached: bool = False

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(400, "Empty query")

    # Cache hit
    cached = app.state.cache.get(req.query, req.category)
    if cached:
        return QueryResponse(**cached, cached=True)

    result = app.state.rag.invoke(req.query, req.category)
    app.state.cache.set(req.query, req.category, {
        "answer": result["answer"],
        "citations": result["citations"],
    })
    return QueryResponse(answer=result["answer"], citations=result["citations"])

@app.get("/health")
async def health():
    return {"status": "ok"}
```

Run: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

---

## 11. Performance Checklist

| Item | Implementation |
|---|---|
| Async ingestion | `asyncio.gather()` over API pages |
| Batch embedding | `batch_size=64` in HuggingFaceEmbeddings |
| Redis cache | SHA-256 keyed, TTL=3600s |
| HNSW tuning | `m=16, ef_construct=100` at index time; `ef=128` at query time |
| BM25 corpus cache | Pickle corpus on first build, reload on restart |
| Qdrant payload index | Mandatory for category/tag filters at scale |

---

## 12. Common Errors & Fixes

| Error | Fix |
|---|---|
| `CollectionNotFound` | Run `create_collection()` before ingestion |
| Embedding dim mismatch | Confirm `size=384` matches bge-small output |
| BM25 returns empty | Ensure corpus built from `page_content`, not empty strings |
| Reranker OOM | Reduce input to reranker from 20 → 10 |
| Redis connection refused | Check `REDIS_URL` env var and Docker status |
| Gemini quota | Switch to `gemini-1.5-flash` or add retry with backoff |
| Slow BM25 at scale | Pickle BM25 index on first build, reload from disk |

---

## 13. Reference Files

- `references/implementations.md` — Extended code: streaming ingestion, BM25 caching,
  async batch embedding, HNSW ef query tuning, LangChain LCEL chain variant,
  full Docker Compose setup, metrics instrumentation.

Read a section from it only when the user needs that specific feature. Do not read the whole
file unless asked.
