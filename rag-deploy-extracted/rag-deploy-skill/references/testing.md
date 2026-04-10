# Smoke Tests for RAG Deployment

## scripts/smoke_test.sh

```bash
#!/bin/bash
# Run after every deploy to verify all services are working
set -e

SERVER="${SERVER_IP:-localhost}"
PASS=0
FAIL=0

green() { echo -e "\033[32m  PASS: $1\033[0m"; PASS=$((PASS+1)); }
red()   { echo -e "\033[31m  FAIL: $1\033[0m"; FAIL=$((FAIL+1)); }
info()  { echo -e "\033[34m  INFO: $1\033[0m"; }

echo ""
echo "════════════════════════════════════════"
echo "  Smoke Tests — $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Server: $SERVER"  
echo "════════════════════════════════════════"

# ── 1. Docker containers running ──────────────────────────
echo ""
echo "--- Container Status ---"
for svc in backend nginx qdrant postgres; do
    STATE=$(docker compose ps $svc --format json 2>/dev/null | \
            python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('State','unknown'))" 2>/dev/null || echo "unknown")
    if [ "$STATE" = "running" ]; then
        green "$svc is running"
    else
        red "$svc is NOT running (state: $STATE)"
    fi
done

# ── 2. Health endpoint ────────────────────────────────────
echo ""
echo "--- Health Check ---"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$SERVER/health 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ]; then
    green "GET /health → 200"
else
    red "GET /health → $HTTP (expected 200)"
fi

# ── 3. Qdrant reachable (from inside Docker) ─────────────
echo ""
echo "--- Qdrant ---"
QDRANT=$(docker compose exec -T backend \
    curl -s -o /dev/null -w "%{http_code}" http://qdrant:6333/healthz 2>/dev/null || echo "000")
if [ "$QDRANT" = "200" ]; then
    green "Qdrant healthz → 200"
else
    red "Qdrant healthz → $QDRANT"
fi

# List collections
info "Qdrant collections:"
docker compose exec -T backend \
    curl -s http://qdrant:6333/collections | python3 -m json.tool 2>/dev/null | grep '"name"' || echo "    (none or error)"

# ── 4. Postgres reachable ─────────────────────────────────
echo ""
echo "--- Postgres ---"
PG=$(docker compose exec -T postgres \
    pg_isready 2>/dev/null && echo "ready" || echo "not ready")
if [ "$PG" = "ready" ]; then
    green "Postgres is ready"
else
    red "Postgres is NOT ready"
fi

# ── 5. Frontend loads ─────────────────────────────────────
echo ""
echo "--- Frontend ---"
FE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$SERVER/ 2>/dev/null || echo "000")
if [ "$FE" = "200" ]; then
    green "GET / (React) → 200"
else
    red "GET / (React) → $FE"
fi

# ── 6. Query endpoint (basic test) ───────────────────────
echo ""
echo "--- Query Endpoint ---"
RESPONSE=$(curl -s --max-time 60 -X POST http://$SERVER/api/query \
    -H "Content-Type: application/json" \
    -d '{"question": "What is an SOP?", "collection": "SOPs"}' 2>/dev/null || echo "")

if echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'answer' in d" 2>/dev/null; then
    ANSWER=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['answer'][:80])" 2>/dev/null)
    green "POST /api/query → has 'answer' field"
    info "Answer preview: $ANSWER..."
else
    red "POST /api/query → missing 'answer' field or error"
    info "Raw response: $RESPONSE"
fi

# ── 7. Webhook endpoint ───────────────────────────────────
echo ""
echo "--- Webhook Endpoint ---"
WH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -X POST http://$SERVER/api/webhook/ \
    -H "Content-Type: application/json" \
    -d '{"method": "ADD", "data": {"id": "smoke-test-001", "content": "smoke test document"}}' \
    2>/dev/null || echo "000")
if [ "$WH" = "202" ]; then
    green "POST /api/webhook/ → 202 Accepted"
else
    red "POST /api/webhook/ → $WH (expected 202)"
fi

# ── 8. RAM check ─────────────────────────────────────────
echo ""
echo "--- Resource Usage ---"
MEM=$(free -m | awk 'NR==2{printf "%s/%s MB (%.0f%%)", $3,$2,$3*100/$2}')
info "Memory: $MEM"

# OOM check
OOM=$(dmesg 2>/dev/null | grep -i "oom\|out of memory\|killed process" | tail -3 || echo "")
if [ -z "$OOM" ]; then
    green "No OOM kills detected"
else
    red "OOM kills detected:"
    echo "$OOM"
fi

# ── Summary ───────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "════════════════════════════════════════"
echo ""

if [ $FAIL -gt 0 ]; then
    echo "  Debug commands:"
    echo "  docker compose logs backend --tail=50"
    echo "  docker compose logs nginx --tail=20"
    echo "  docker compose ps"
    exit 1
fi
```

Make executable:
```bash
chmod +x scripts/smoke_test.sh
```

Run after deploy:
```bash
./scripts/smoke_test.sh
# Or with remote server IP:
SERVER_IP=65.21.244.158 ./scripts/smoke_test.sh
```

---

## Manual debug commands

```bash
# All container status
docker compose ps

# Backend logs (most important)
docker compose logs backend --tail=50 -f

# Check backend started properly (look for "Models loaded" or "Application startup complete")
docker compose logs backend | grep -i "startup\|model\|error\|loaded"

# Check Nginx errors
docker compose logs nginx --tail=20

# Check memory
free -h
docker stats --no-stream

# Check OOM kills
dmesg | grep -i "oom\|killed" | tail -10

# Enter backend container for debugging
docker compose exec backend bash
# Then inside: python -c "from chain.rag_chain import SmartRAGChain; print('imports OK')"

# Check Qdrant collections directly
curl http://localhost:6333/collections | python3 -m json.tool

# Restart only one service
docker compose restart backend

# Full restart (nuclear option — keeps data volumes)
docker compose down && docker compose up -d
```
