"""Webhook endpoints for real-time Qdrant synchronization.

Pipeline (identical to storage/ingest.py + ingestion/multi_fetcher.py):
  1. Smart-map raw JSON  →  entity_type + collection
  2. Clean via per-entity cleaner from multi_fetcher.py
  3. Chunk via chunk_documents()
  4. Embed via get_embedder()
  5. Build PointStruct (same payload schema as ingest.py)
  6. DELETE old points by source_id (idempotent)
  7. UPSERT new points in batches of 64
"""

import os
import logging
import hashlib
from typing import Literal, Optional, Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, status, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, PointStruct

from langchain_core.documents import Document

from embeddings.embedder import get_embedder
from ingestion.chunker import chunk_documents
from ingestion.multi_fetcher import (
    _clean_sop,
    _clean_deviation,
    _clean_capa,
    _clean_decision,
    _clean_audit,
)
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# ── Auth ────────────────────────────────────────────────────────────────────
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "super-secret-webhook-key")
api_key_header = APIKeyHeader(name="x-webhook-secret", auto_error=True)


def verify_webhook_secret(api_key: str = Depends(api_key_header)):
    if api_key != WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret signature",
        )
    return api_key


# ── Collection map (mirrors multi_ingest.py) ────────────────────────────────
COLLECTION_MAP: Dict[str, str] = {
    "sops":       os.getenv("COLLECTION_SOPS",       "docs_sops"),
    "deviations": os.getenv("COLLECTION_DEVIATIONS", "docs_deviations"),
    "capas":      os.getenv("COLLECTION_CAPAS",      "docs_capas"),
    "decisions":  os.getenv("COLLECTION_DECISIONS",  "docs_decisions"),
    "audits":     os.getenv("COLLECTION_AUDITS",     "docs_audits"),
}

# Maps entity_type → the cleaner function from multi_fetcher
CLEANER_MAP = {
    "sops":       _clean_sop,
    "deviations": _clean_deviation,
    "capas":      _clean_capa,
    "decisions":  _clean_decision,
    "audits":     _clean_audit,
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_qdrant_id(chunk_id: str) -> int:
    """Deterministic integer ID — same method as api_fetcher.py."""
    return int(hashlib.md5(chunk_id.encode()).hexdigest(), 16) % (2**63 - 1)


def _build_points(chunks: List[Document]) -> List[PointStruct]:
    """Embed chunks and build PointStructs identical to ingest.py payload."""
    embedder = get_embedder()
    texts = [c.page_content for c in chunks]
    embeddings = embedder.embed_documents(texts)

    points = []
    for chunk, emb in zip(chunks, embeddings):
        chunk_id = chunk.metadata.get("chunk_id", "")
        points.append(
            PointStruct(
                id=_make_qdrant_id(chunk_id) if chunk_id else _make_qdrant_id(chunk.page_content[:64]),
                vector=emb,
                payload={
                    # Primary searchable text
                    "page_content": chunk.page_content,
                    # Flat top-level fields (same as ingest.py)
                    "title":      chunk.metadata.get("title", ""),
                    "ref_number": chunk.metadata.get("ref_number", ""),
                    "doc_type":   chunk.metadata.get("doc_type", ""),
                    "status":     chunk.metadata.get("status", ""),
                    "source_id":  chunk.metadata.get("source_id", ""),
                    "chunk_id":   chunk.metadata.get("chunk_id", ""),
                    # Nested metadata for LangChain retriever compatibility
                    "metadata":   chunk.metadata,
                },
            )
        )
    return points


# ── Background worker ────────────────────────────────────────────────────────

def _process_sync(entity_type: str, action: str, raw_payload: dict):
    """
    Synchronous background task (runs in thread pool via FastAPI).

    For 'delete':         removes all points with matching source_id.
    For 'create'/'update': clean → chunk → embed → delete-old → upsert.
    """
    collection_name = COLLECTION_MAP.get(entity_type)
    if not collection_name:
        logging.error(f"[WEBHOOK] Unknown entity_type: {entity_type}")
        return

    qdrant_url     = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY") or None
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    # Determine the canonical source_id
    cleaner   = CLEANER_MAP[entity_type]
    doc: Document | None = cleaner(raw_payload)

    if doc is None and action in ("create", "update"):
        logging.warning(f"[WEBHOOK] Cleaner returned None for payload: {raw_payload}")
        return

    source_id = (doc.metadata.get("source_id") if doc else None) or raw_payload.get("id")
    if not source_id:
        logging.error("[WEBHOOK] Could not determine source_id — aborting.")
        return

    # ── Ensure the payload index exists (for fast filtering) ────────────────
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="source_id",
            field_schema="keyword",
        )
    except Exception:
        pass  # Already exists

    # ── Step 1: Delete old points for this document ──────────────────────────
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="source_id", match=MatchValue(value=str(source_id)))]
            ),
        )
        logging.info(f"[WEBHOOK] Deleted old vectors for source_id={source_id} in '{collection_name}'")
    except Exception as e:
        logging.warning(f"[WEBHOOK] Delete step failed (may be first insert): {e}")

    # ── Step 2: Insert new points (skip for delete action) ───────────────────
    if action == "delete":
        logging.info(f"[WEBHOOK] DELETE complete for {source_id}")
        return

    # Chunk
    chunks = chunk_documents([doc])
    if not chunks:
        logging.warning(f"[WEBHOOK] No chunks produced for {source_id}")
        return

    logging.info(f"[WEBHOOK] {len(chunks)} chunks produced for {source_id}")

    # Embed + build points
    try:
        points = _build_points(chunks)
    except Exception as e:
        logging.error(f"[WEBHOOK] Embedding failed for {source_id}: {e}")
        return

    # Upsert in batches of 64 (same as ingest.py)
    batch_size = 64
    try:
        for i in range(0, len(points), batch_size):
            client.upsert(
                collection_name=collection_name,
                points=points[i : i + batch_size],
            )
        logging.info(
            f"[WEBHOOK] SUCCESS: {len(points)} points upserted into "
            f"'{collection_name}' for source_id={source_id}"
        )
    except Exception as e:
        logging.error(f"[WEBHOOK] Upsert failed for {source_id}: {e}")


# ── Route ────────────────────────────────────────────────────────────────────

async def _handle_sync(
    background_tasks: BackgroundTasks,
    payload_raw: Dict[str, Any],
    forced_action: Optional[str] = None
):
    """Internal helper to detect entity_type and queue background sync."""
    action      = (forced_action or payload_raw.get("action", "update")).lower()
    entity_type = payload_raw.get("entity_type")

    # ── Auto-detect entity_type from key names ───────────────────────────────
    if not entity_type:
        if "deviation_number" in payload_raw:
            entity_type = "deviations"
        elif "sop_number" in payload_raw:
            entity_type = "sops"
        elif "capa_number" in payload_raw:
            entity_type = "capas"
        elif "decision_number" in payload_raw:
            entity_type = "decisions"
        elif "audit_number" in payload_raw or "finding_number" in payload_raw:
            entity_type = "audits"
        else:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cannot determine entity_type. "
                    "Pass 'entity_type' explicitly or include a recognisable "
                    "key (deviation_number, capa_number, sop_number, etc.)."
                ),
            )

    if entity_type not in COLLECTION_MAP:
        raise HTTPException(status_code=422, detail=f"Unknown entity_type: {entity_type}")

    # ── Determine doc id for response message ────────────────────────────────
    doc_id = (
        payload_raw.get("deviation_number")
        or payload_raw.get("sop_number")
        or payload_raw.get("capa_number")
        or payload_raw.get("decision_number")
        or payload_raw.get("audit_number")
        or payload_raw.get("finding_number")
        or payload_raw.get("id", "unknown")
    )

    # Queue the sync job (non-blocking — real-time)
    background_tasks.add_task(_process_sync, entity_type, action, payload_raw)

    return {
        "status":    "accepted",
        "message":   f"Sync job queued for {doc_id}",
        "entity":    entity_type,
        "action":    action,
        "collection": COLLECTION_MAP[entity_type],
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/qdrant/sync", status_code=status.HTTP_202_ACCEPTED)
async def handle_qdrant_webhook_post(
    background_tasks: BackgroundTasks,
    payload_raw: Dict[str, Any],
    secret: str = Depends(verify_webhook_secret),
):
    """
    Accepts raw entity JSON from the external backend and queues a real-time
    sync job. Supported actions: create | update | delete.
    """
    return await _handle_sync(background_tasks, payload_raw)


@router.put("/qdrant/sync", status_code=status.HTTP_202_ACCEPTED)
async def handle_qdrant_webhook_put(
    background_tasks: BackgroundTasks,
    payload_raw: Dict[str, Any],
    secret: str = Depends(verify_webhook_secret),
):
    """
    Idempotent PUT endpoint for replacing an existing document in Qdrant.
    Forces action to 'update' regardless of payload content.
    """
    return await _handle_sync(background_tasks, payload_raw, forced_action="update")
