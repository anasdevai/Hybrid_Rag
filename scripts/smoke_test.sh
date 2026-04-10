#!/bin/bash
set -e

SERVER="${SERVER_IP:-localhost}"
PASS=0; FAIL=0

green() { echo -e "\033[32m  PASS: $1\033[0m"; PASS=$((PASS+1)); }
red()   { echo -e "\033[31m  FAIL: $1\033[0m"; FAIL=$((FAIL+1)); }
info()  { echo -e "\033[34m  INFO: $1\033[0m"; }

echo ""
echo "════════════════════════════════════════"
echo "  Smoke Tests — $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Server: $SERVER"
echo "════════════════════════════════════════"

# 1. Container status
echo ""
echo "--- Containers ---"
for svc in backend nginx db; do
    STATE=$(docker compose ps $svc --format json 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('State','unknown'))" 2>/dev/null || echo "unknown")
    [ "$STATE" = "running" ] && green "$svc running" || red "$svc NOT running ($STATE)"
done

# 2. Health endpoint
echo ""
echo "--- Health ---"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$SERVER/health 2>/dev/null || echo "000")
[ "$HTTP" = "200" ] && green "GET /health → 200" || red "GET /health → $HTTP"

# 3. Frontend
echo ""
echo "--- Frontend ---"
FE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$SERVER/ 2>/dev/null || echo "000")
[ "$FE" = "200" ] && green "GET / → 200" || red "GET / → $FE"

# 4. Postgres
echo ""
echo "--- Postgres ---"
PG=$(docker compose exec -T db pg_isready 2>/dev/null && echo "ready" || echo "not ready")
[ "$PG" = "ready" ] && green "Postgres ready" || red "Postgres NOT ready"

# 5. RAM check
echo ""
echo "--- Resources ---"
MEM=$(free -m | awk 'NR==2{printf "%s/%s MB (%.0f%%)", $3,$2,$3*100/$2}')
info "Memory: $MEM"
OOM=$(dmesg 2>/dev/null | grep -i "oom\|out of memory\|killed process" | tail -3 || echo "")
[ -z "$OOM" ] && green "No OOM kills" || red "OOM kills detected: $OOM"

# Summary
echo ""
echo "════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "════════════════════════════════════════"
echo ""

if [ $FAIL -gt 0 ]; then
    echo "  Debug: docker compose logs backend --tail=50"
    exit 1
fi
