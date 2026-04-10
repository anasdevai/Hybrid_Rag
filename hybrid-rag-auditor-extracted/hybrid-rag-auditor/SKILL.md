---
name: hybrid-rag-auditor
description: >
  Deeply tests and audits a Hybrid RAG (Retrieval-Augmented Generation) chatbot system and produces a
  detailed scored audit report with actionable recommendations. Use this skill whenever the user wants
  to evaluate, test, or improve a RAG chatbot — especially one using FastAPI, LangChain, React,
  PostgreSQL/pgAdmin, and Qdrant. Trigger this skill when the user mentions "audit my RAG", "test my
  chatbot", "check my RAG pipeline", "RAG quality report", "evaluate my hybrid search", "test my
  embeddings", "check Qdrant collections", "test webhook", or any combination of RAG + quality +
  testing keywords. Also trigger when the user wants to verify security, credential exposure, LLM
  parameter tuning, reranker config, or chat session storage in their AI chatbot backend.
---

# Hybrid RAG Chatbot Auditor

Produces a **detailed, scored audit report** for a Hybrid RAG chatbot system. The report scores each
dimension 1–10 and provides specific findings and recommended fixes.

---

## Tech Stack This Skill Targets

| Layer | Technology |
|---|---|
| Backend API | FastAPI |
| AI Orchestration | LangChain |
| Frontend | React |
| Relational DB | PostgreSQL (pgAdmin) |
| Vector DB | Qdrant |
| Embeddings | Multi-endpoint ingestion → Qdrant collections |

---

## Audit Dimensions

Run checks in this order. Each produces a **score (1–10)**, **findings**, and **recommendations**.

### 1. 🔐 Security & Credential Exposure Audit
**Priority: CRITICAL — always run first.**

Check for:
- Hardcoded API keys, DB passwords, Qdrant API keys in source files (`.env`, `.py`, `.ts`, `.tsx`, `.json`)
- `.env` files committed to git (check `.gitignore`)
- Secrets exposed in frontend bundles (React build artifacts)
- Qdrant URL/port exposed to public without auth
- FastAPI endpoints missing authentication middleware
- CORS policy — is it `allow_origins=["*"]`? Flag as risk.
- PostgreSQL connection string in plaintext anywhere in code

**How to check:**
```bash
# Search for common credential patterns
grep -rn "sk-" . --include="*.py" --include="*.ts" --include="*.env"
grep -rn "password" . --include="*.py" --include="*.ts"
grep -rn "API_KEY\|SECRET\|TOKEN" . --include="*.py" --include="*.ts" --include="*.tsx"
grep -rn "qdrant" . --include="*.py" | grep -i "api_key\|url\|host"
cat .gitignore | grep -E "\.env|secret|credential"
```

Score deductions:
- Any hardcoded secret in committed code → max score 2
- `.env` not in `.gitignore` → -3
- CORS wildcard on production → -2
- Qdrant unauthenticated on public port → -2

---

### 2. 🧠 CoT System Prompt & LLM Parameters

Check the LangChain chain configuration for:

**System Prompt Quality:**
- Is a Chain-of-Thought (CoT) instruction present? (e.g., "Think step by step before answering")
- Does the prompt define the assistant's persona, scope, and limitations?
- Is the prompt injecting retrieved context correctly? (`{context}` variable)
- Is there a fallback instruction when no relevant context is found?
- Prompt length — is it excessively long (>2000 tokens) or too sparse (<50 tokens)?

**LLM Parameters:**
- `temperature`: Ideal range for RAG is 0.0–0.3. Flag if > 0.5.
- `max_tokens` / `max_length`: Is it set? Unset = unpredictable costs.
- `top_p`, `frequency_penalty`: Document their values.
- Which LLM model is used? Is it appropriate for the use case?
- Is streaming enabled? Check for proper error handling in streaming mode.

**How to check:**
```python
# Look for chain initialization
grep -rn "ChatOpenAI\|ChatAnthropic\|temperature\|max_tokens" . --include="*.py"
grep -rn "SystemMessage\|system_prompt\|SYSTEM_TEMPLATE" . --include="*.py"
grep -rn "PromptTemplate\|ChatPromptTemplate" . --include="*.py"
```

Score deductions:
- No CoT instruction → -2
- Temperature > 0.5 for RAG → -2
- No fallback for missing context → -1
- `{context}` not injected into prompt → -3

---

### 3. 🔍 Hybrid Search & Reranker Configuration

**Semantic Search (Qdrant):**
- What embedding model is used? (e.g., `text-embedding-ada-002`, `all-MiniLM-L6-v2`)
- Embedding dimension — does it match Qdrant collection config?
- Search type: dense, sparse, or hybrid? Hybrid = dense + sparse (BM25/SPLADE).
- `top_k` value — is it reasonable (5–20)?
- Score threshold set? Low threshold = noise in results.

**Reranker:**
- Is a reranker present? (e.g., Cohere Rerank, cross-encoder, `FlashrankRerank`)
- If yes: what model? What `top_n` value after reranking?
- If no: flag as improvement opportunity.

**How to check:**
```python
grep -rn "rerank\|Rerank\|cross.encoder\|FlashrankRerank" . --include="*.py"
grep -rn "similarity_search\|search\|top_k\|score_threshold" . --include="*.py"
grep -rn "QdrantVectorStore\|Qdrant(" . --include="*.py"
grep -rn "SparseVector\|BM25\|SPLADE\|hybrid" . --include="*.py"
```

Score deductions:
- No reranker → -2
- No score threshold → -1
- Embedding dimension mismatch → -4
- `top_k` > 50 without filtering → -1

---

### 4. 🗄️ Qdrant Vector Database — Collection Structure

**Per-collection checks:**
- List all collections: `GET /collections` on Qdrant API
- Each data source should have its **own collection** — verify isolation
- Collection config: vector size, distance metric (Cosine preferred for semantic search)
- Payload schema: does each point have `source`, `chunk_id`, `metadata`?
- Index type: HNSW params (`m`, `ef_construction`) — are they set or default?
- Collection is not empty — verify point count > 0

**How to check (via Qdrant REST API or Python client):**
```python
from qdrant_client import QdrantClient
client = QdrantClient(url="http://localhost:6333")

# List collections
collections = client.get_collections()
for col in collections.collections:
    info = client.get_collection(col.name)
    print(f"{col.name}: {info.points_count} points, vector_size={info.config.params.vectors.size}")
```

**Webhook/data ingestion test:**
- POST test payload to each ingestion endpoint
- Verify embedding is created and stored in correct Qdrant collection
- Verify point count increases after POST

Score deductions:
- All data in one collection → -3
- Missing metadata payload → -2
- Empty collection → -3
- Wrong distance metric → -1

---

### 5. 🐘 PostgreSQL / pgAdmin — Auth & Session Storage

**Authentication:**
- Is user auth implemented? (JWT, OAuth, session tokens)
- Passwords stored as bcrypt/argon2 hashes? Never plaintext.
- Token expiry set?
- Is there a `users` table with proper schema?

**Chat Session Storage:**
- Is chat history persisted to PostgreSQL?
- Schema check: `chat_sessions` table with `session_id`, `user_id`, `messages` (JSONB), `created_at`
- Is session isolated per user? (No cross-user data leakage)
- Is there an index on `session_id` and `user_id`?
- LangChain memory: `PostgresChatMessageHistory` or custom?

**How to check:**
```sql
-- Run these in pgAdmin
\dt  -- list all tables
SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users';
SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'chat_sessions';
SELECT COUNT(*) FROM chat_sessions;
EXPLAIN SELECT * FROM chat_sessions WHERE session_id = 'test';
```

Score deductions:
- No password hashing → max score 1
- No session isolation → -3
- No index on session_id → -2
- Chat history not persisted → -2

---

### 6. 🔗 Webhook & API Endpoint Testing

**For each data ingestion endpoint:**
- Test with valid payload → expect 200 + confirmation
- Test with invalid/missing fields → expect 422 with clear error
- Test with oversized payload → expect 413 or graceful error
- Test duplicate data → does it upsert or create duplicates in Qdrant?
- Check rate limiting — is it implemented?

**FastAPI endpoint audit:**
```bash
# Discover all routes
curl http://localhost:8000/openapi.json | python3 -m json.tool | grep '"path"'

# Test webhook
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "test", "content": "sample document text"}'
```

**Webhook-specific:**
- Is there a signature verification step? (HMAC, secret header)
- Are webhook events idempotent?
- Is there a webhook delivery log/retry mechanism?

Score deductions:
- No input validation → -2
- No rate limiting → -1
- Duplicate data on re-POST → -2
- No webhook signature verification → -2

---

### 7. ⚛️ React Frontend — Integration Quality

**Check:**
- Is the API base URL hardcoded or from environment variable?
- Are API keys or tokens stored in `localStorage`? (Flag — use `httpOnly` cookies instead)
- Error handling: does the UI show meaningful errors when API fails?
- Streaming: if backend streams, does frontend handle `EventSource`/SSE correctly?
- Auth token attached to requests? (Authorization header)

```bash
grep -rn "localStorage\|sessionStorage" src/ --include="*.tsx" --include="*.ts"
grep -rn "REACT_APP_\|import.meta.env" src/ --include="*.tsx"
grep -rn "hardcode\|http://localhost" src/ --include="*.tsx" --include="*.ts"
```

Score deductions:
- API keys in localStorage → -3
- Hardcoded localhost URLs in production build → -2
- No error handling on API calls → -2

---

## Running the Full Audit

### Step 1: Collect the codebase
Ask the user for access to their project (uploaded zip, git repo path, or directory listing).

### Step 2: Run all 7 checks
Work through each dimension systematically. For each:
1. Run the relevant grep/curl/SQL commands
2. Note all findings
3. Assign a score 1–10
4. Write specific recommendations

### Step 3: Generate the Audit Report
Use the report template in `references/report-template.md`.

The report must include:
- Executive Summary with overall score (average of all dimensions)
- Scorecard table
- Per-dimension findings
- Priority fix list (Critical → High → Medium → Low)
- "Path to 10/10" section with concrete steps

---

## Scoring Guide

| Score | Meaning |
|---|---|
| 9–10 | Production-ready, best practices followed |
| 7–8 | Good, minor improvements needed |
| 5–6 | Functional but significant gaps |
| 3–4 | Major issues, not production-ready |
| 1–2 | Critical failures, security risks |

---

## Output Format

Always produce the report as a `.docx` file using the docx skill. See `references/report-template.md` for structure.

Read `/mnt/skills/public/docx/SKILL.md` before generating the report file.
