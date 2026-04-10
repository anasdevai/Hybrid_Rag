"""
RAG Chatbot — standalone FastAPI service.
Endpoints:  POST /rag/query
            POST /rag/query/smart
            GET  /rag/health
Runs on port 8001, proxied via nginx at /rag/
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List, Any

from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore

from embeddings.embedder import get_embedder
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.reranker import CrossEncoderReranker
from retrieval.federated_retriever import FederatedRetriever
from chain.rag_chain import SmartRAGChain

from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="RAG Chatbot API", root_path="/rag")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )
    embedder = get_embedder()
    reranker = CrossEncoderReranker(top_n=5)

    collection_map = {
        "sops":       os.getenv("COLLECTION_SOPS",       "docs_sops"),
        "deviations": os.getenv("COLLECTION_DEVIATIONS", "docs_deviations"),
        "capas":      os.getenv("COLLECTION_CAPAS",      "docs_capas"),
        "audits":     os.getenv("COLLECTION_AUDITS",     "docs_audits"),
        "decisions":  os.getenv("COLLECTION_DECISIONS",  "docs_decisions"),
    }

    vectorstores = {
        section: QdrantVectorStore(client=client, collection_name=col, embedding=embedder)
        for section, col in collection_map.items()
    }

    federated = FederatedRetriever(client=client, vectorstores=vectorstores, reranker=reranker)
    for section, col in collection_map.items():
        federated.retrievers[section].collection_name = col

    app.state.rag = SmartRAGChain(federated)
    print("[rag-chatbot] Ready.")


# ── Schemas ──────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    category: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]
    suggestions: List[str] = []
    retrieval_stats: Dict[str, Any]
    routed_to: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
@app.post("/query/smart", response_model=QueryResponse)
async def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(400, "Empty query")
    result = app.state.rag.invoke(req.query)
    return QueryResponse(
        answer=result["answer"],
        citations=result["citations"],
        suggestions=result.get("suggestions", []),
        retrieval_stats=result["retrieval_stats"],
        routed_to=result.get("routed_to", ""),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rag-chatbot"}
