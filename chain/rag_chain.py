"""
chain/rag_chain.py

Two chain classes:
  - HybridRAGChain     : original single-collection chain (backward compat.)
  - SmartRAGChain      : routes query to relevant collections only, returns
                         clean prose answer + citations + dynamic suggestions.
"""

import time
import re
import json
from typing import Dict, List, Tuple

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

from retrieval.hybrid_retriever import HybridRetriever
from retrieval.reranker import CrossEncoderReranker
from retrieval.context_builder import build_context
from retrieval.federated_retriever import FederatedRetriever
from retrieval.query_router import route_query, describe_route
import os


# ─────────────────────────────────────────────
# Shared LLM
# ─────────────────────────────────────────────
def get_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        temperature=temperature,
        max_output_tokens=2048,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        max_retries=6,
        thinking_budget=0,
    )


# ─────────────────────────────────────────────
# ORIGINAL SINGLE-COLLECTION CHAIN (unchanged)
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are SOPSearch AI - a compliance assistant for SOPs and regulatory processes.
Answer from context only. Be concise. If not found say: "Information not available in the knowledge base."
Do NOT fabricate document numbers or dates.
"""
USER_PROMPT = "## Context\n{context}\n\n## Question\n{question}\n\nAnswer:"


class HybridRAGChain:
    def __init__(self, retriever: HybridRetriever, reranker: CrossEncoderReranker):
        self.retriever = retriever
        self.reranker  = reranker
        self.llm = get_llm()
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT), ("human", USER_PROMPT),
        ])

    def invoke(self, query: str, category_filter: str = None) -> dict:
        self.retriever.category_filter = category_filter
        raw  = self.retriever.invoke(query)
        rnk  = self.reranker.rerank(query, raw)
        ctx, cits = build_context(rnk)
        ans = (self.prompt | self.llm | StrOutputParser()).invoke({"context": ctx, "question": query})
        return {"answer": ans, "citations": cits, "num_docs_retrieved": len(raw), "num_docs_reranked": len(rnk)}


# ─────────────────────────────────────────────────────────────────
# SMART RAG CHAIN — routes to relevant collection(s) only
# ─────────────────────────────────────────────────────────────────

SMART_SYSTEM = """\
You are SOPSearch AI, an expert regulatory compliance assistant for SOPs, 
Deviations, CAPAs, Audit Findings, and Decisions.

Think step by step before answering. Use ONLY the retrieved context blocks.

## MANDATORY RESPONSE FORMAT — follow exactly, no exceptions:

### Direct Answer
[2-4 sentences. Directly answer the question. If nothing found, state clearly 
what IS available: "No SOP on access control found. Available SOPs cover: [list them]"]

### Key Points
- [Specific point from context — include document ID]
- [Specific point from context — include document ID]  
- [Specific point from context — include document ID]
(max 5 bullets. Skip this section only if zero relevant content retrieved.)

### Summary
[1-2 sentences. Decision-ready conclusion.]
For risk questions append: 🟢 LOW / 🟡 MEDIUM / 🔴 HIGH
For interpretation questions append a recommendation.

### Sources
| Document ID | Title | Type | Relevance |
|-------------|-------|------|-----------|
| [ref] | [title] | [type] | [one phrase why retrieved] |
(One row per document. NEVER merge IDs on one line.)

---CITATIONS---
[
  {"ref": "DOC-ID", "title": "Document title", "type": "SOP", "excerpt": "one sentence excerpt"}
]

---SUGGESTIONS---
["specific follow-up 1 using doc IDs from context", "specific follow-up 2", "specific follow-up 3"]

## RULES
- Answer in the same language as the question (German → German, English → English).
- Never invent document numbers, dates, or facts not in the context.
- Never merge source IDs together (e.g. never write "SOP-001SOP-002").
- Always separate ### Sources table from ---CITATIONS--- block.
- Suggestions must reference specific document IDs found in context.
- If context has no answer: still complete the format, explain what was found instead.
"""

SMART_USER = """\
## Retrieved Context
{context}

## User Question
{question}

Provide your full answer, then the ---CITATIONS--- block, then the ---SUGGESTIONS--- block:
"""


def _build_unified_context(docs: List[Document], prefix_label: str) -> Tuple[str, List[dict]]:
    """Build a numbered context string from retrieved docs, regardless of collection."""
    if not docs:
        return "", []

    parts, raw_cits = [], []
    total = 0
    MAX = 14000

    for i, doc in enumerate(docs):
        text = doc.page_content.strip()
        if not text or total + len(text) > MAX:
            break

        meta     = doc.metadata
        ref      = meta.get("ref_number", "")
        title    = meta.get("title", "")
        doc_type = meta.get("doc_type", prefix_label)
        status   = meta.get("status", "")

        header_parts = [f"[{i}]", doc_type.upper()]
        if ref:    header_parts.append(ref)
        if title:  header_parts.append(f'"{title}"')
        if status: header_parts.append(f"({status})")
        header = " ".join(header_parts)

        parts.append(f"{header}\n{text}")
        raw_cits.append({
            "ref":    ref or f"#{i}",
            "title":  title,
            "type":   doc_type,
            "status": status,
            "score":  round(float(meta.get("rerank_score", 0.0)), 4),
        })
        total += len(text)

    return "\n\n---\n\n".join(parts), raw_cits


def _parse_answer_citations_suggestions(raw: str) -> Tuple[str, List[dict], List[str]]:
    """
    Parse the LLM output into:
      answer     : clean prose text
      citations  : list of dicts from the ---CITATIONS--- block
      suggestions: list of strings from the ---SUGGESTIONS--- block
    """
    answer      = raw
    citations   = []
    suggestions = []

    # ── Extract ---SUGGESTIONS--- ──
    sug_match = re.search(r'---SUGGESTIONS---\s*(\[.*?\])', raw, re.DOTALL | re.IGNORECASE)
    if sug_match:
        try:    suggestions = json.loads(sug_match.group(1))
        except: suggestions = []
        raw = raw[:sug_match.start()].strip()

    # ── Extract ---CITATIONS--- ──
    cit_match = re.search(r'---CITATIONS---\s*(\[.*?\])', raw, re.DOTALL | re.IGNORECASE)
    if cit_match:
        try:    citations = json.loads(cit_match.group(1))
        except: citations = []
        answer = raw[:cit_match.start()].strip()
    else:
        answer = raw.strip()

    # Clamp suggestions
    suggestions = [s for s in suggestions if isinstance(s, str)][:4]

    return answer, citations, suggestions


from langchain_core.messages import SystemMessage
from langchain_core.prompts import HumanMessagePromptTemplate

class SmartRAGChain:
    """
    Intelligent RAG chain that:
      1. Routes the query to the relevant collection(s) only.
      2. Does Hybrid Search (Dense + BM25) + Cross-Encoder reranking.
      3. Returns: clean prose answer | citations | dynamic suggestions.
    """

    def __init__(self, federated_retriever: FederatedRetriever):
        self.federated = federated_retriever
        self.llm = get_llm()
        self.prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=SMART_SYSTEM),
            HumanMessagePromptTemplate.from_template(SMART_USER),
        ])

    def invoke(self, query: str) -> dict:
        t0 = time.time()

        # ── Step 1: Route query to relevant collections ──
        target_sections = route_query(query)
        routed_label    = describe_route(target_sections)
        print(f"  [router] '{query[:60]}' -> {target_sections}")

        # ── Step 2: Hybrid search on targeted collections only ──
        all_docs: List[Document] = []
        per_section_counts: Dict[str, int] = {}

        for section in target_sections:
            retriever = self.federated.retrievers.get(section)
            if not retriever:
                continue
            try:
                docs = retriever.invoke(query)
                # Rerank within this section
                top_n = 5 if len(target_sections) == 1 else 3
                ranked = self.federated.reranker.rerank_top_n(query, docs, top_n)
                # Tag each doc with its section
                for d in ranked:
                    d.metadata["_section"] = section
                all_docs.extend(ranked)
                per_section_counts[section] = len(ranked)
            except Exception as e:
                print(f"  [router] Warning: retrieval failed for '{section}': {e}")
                per_section_counts[section] = 0

        if not all_docs:
            return {
                "answer":          "No relevant information found in the knowledge base for your query.",
                "citations":       [],
                "suggestions":     ["Ask about a specific SOP number", "Search for related deviations", "Check CAPA status"],
                "retrieval_stats": {"searched": target_sections, "total_docs": 0, "latency_ms": round((time.time()-t0)*1000, 1)},
                "routed_to":       routed_label,
            }

        # ── Step 3: Build unified context ──
        context_str, raw_cits = _build_unified_context(all_docs, "document")

        # ── Step 4: LLM generation ──
        raw_answer = (self.prompt | self.llm | StrOutputParser()).invoke({
            "context":  context_str,
            "question": query,
        })

        # ── Step 5: Parse answer, citations, suggestions ──
        answer, llm_citations, suggestions = _parse_answer_citations_suggestions(raw_answer)

        # Merge LLM-parsed citations with raw retrieval metadata for richer response
        final_citations = []
        used_refs = set()
        for lc in llm_citations:
            ref = lc.get("ref", "")
            # Try to enrich from raw_cits
            match = next((r for r in raw_cits if ref in r.get("ref", "") or (r.get("title") and r["title"] in lc.get("title", ""))), None)
            entry = {
                "ref":     ref,
                "title":   lc.get("title", match.get("title","") if match else ""),
                "type":    lc.get("type", match.get("type","") if match else ""),
                "excerpt": lc.get("excerpt", ""),
                "status":  match.get("status","") if match else "",
                "score":   match.get("score", 0.0) if match else 0.0,
            }
            if ref not in used_refs:
                final_citations.append(entry)
                used_refs.add(ref)

        # Fall back to raw citations if LLM did not produce any
        if not final_citations:
            final_citations = raw_cits

        # ── Step 6: Assemble full Audit Vault snapshots ──
        metadata_snapshot = []
        audit_log_snapshot = []
        
        seen_docs = set()
        for doc in all_docs:
            source_id = doc.metadata.get("source_id")
            if source_id not in seen_docs:
                metadata_snapshot.append(doc.metadata.get("full_metadata", doc.metadata))
                audit_log_snapshot.extend(doc.metadata.get("audit_trail", []))
                seen_docs.add(source_id)

        latency_ms = round((time.time() - t0) * 1000, 1)

        return {
            "answer":      answer,
            "citations":   final_citations,
            "suggestions": suggestions,
            "retrieval_stats": {
                "searched":     target_sections,
                "per_section":  per_section_counts,
                "total_docs":   len(all_docs),
                "latency_ms":   latency_ms,
            },
            "routed_to":   routed_label,
            "cached":      False,
            # Audit Vault Fields
            "metadata_snapshot":  metadata_snapshot,
            "audit_log_snapshot": audit_log_snapshot,
            "action_metadata": {
                "query": query,
                "routing": target_sections,
                "latency_ms": latency_ms,
                "timestamp": time.time(),
                "model": os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            }
        }


# Keep FederatedRAGChain as alias for backward compat
FederatedRAGChain = SmartRAGChain
