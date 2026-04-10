# CI/CD Pipeline for RAG Deployment

## deploy.sh — place in project root on server

```bash
#!/bin/bash
set -e   # Exit on any error

PROJECT_DIR="/opt/$(basename $(pwd))"
COMPOSE="docker compose"

echo ""
echo "════════════════════════════════════════"
echo "  RAG Deploy — $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════"

# ── Step 1: Pull latest code ──────────────────────────────
echo ""
echo ">>> [1/5] Pulling latest code from git..."
git pull origin main

# ── Step 2: Rebuild backend only ─────────────────────────
# Qdrant and Postgres are NEVER restarted (data safety)
echo ""
echo ">>> [2/5] Rebuilding backend image..."
$COMPOSE build backend

# ── Step 3: Restart only backend + nginx ─────────────────
echo ""
echo ">>> [3/5] Restarting backend and nginx..."
$COMPOSE up -d --no-deps backend nginx

# ── Step 4: Wait for backend to be healthy ───────────────
echo ""
echo ">>> [4/5] Waiting for backend to be healthy..."
MAX_WAIT=90
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    STATUS=$($COMPOSE ps backend --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health','unknown'))" 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "healthy" ]; then
        echo "    Backend is healthy after ${WAITED}s"
        break
    fi
    echo "    Waiting... (${WAITED}s / ${MAX_WAIT}s) — status: $STATUS"
    sleep 5
    WAITED=$((WAITED + 5))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "    WARNING: Backend did not reach healthy state in ${MAX_WAIT}s"
    echo "    Check logs: docker compose logs backend --tail=30"
fi

# ── Step 5: Cleanup and status ───────────────────────────
echo ""
echo ">>> [5/5] Cleaning up old images..."
docker image prune -f

echo ""
echo "════════════════════════════════════════"
echo "  Status after deploy:"
echo "════════════════════════════════════════"
$COMPOSE ps

echo ""
echo "  Deploy complete. Run smoke tests:"
echo "  ./scripts/smoke_test.sh"
echo ""
```

Make executable:
```bash
chmod +x deploy.sh
```

---

## Local machine alias (add to ~/.zshrc or ~/.bashrc)

```bash
# Replace SERVER_IP and PROJECT_NAME
alias deploy-rag="git push origin main && ssh root@65.21.244.158 'cd /opt/PROJECT_NAME && ./deploy.sh'"
```

Usage: just type `deploy-rag` from local machine.

---

## GitHub Actions workflow (optional — automated on push)

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Deploy to server
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_IP }}
          username: root
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/PROJECT_NAME
            ./deploy.sh
            ./scripts/smoke_test.sh

      - name: Notify on failure
        if: failure()
        run: echo "Deploy failed — check server logs"
```

**GitHub Secrets to add:**
- `SERVER_IP` → `65.21.244.158`
- `SSH_PRIVATE_KEY` → contents of `~/.ssh/id_rsa` (your private key)

**Setup SSH key on server:**
```bash
# On local machine
ssh-keygen -t ed25519 -C "github-actions-deploy"
# Copy public key to server
ssh-copy-id -i ~/.ssh/id_ed25519.pub root@65.21.244.158
# Add private key to GitHub Secrets
cat ~/.ssh/id_ed25519
```

---

## What NEVER gets restarted during deploy

| Service | During deploy | Reason |
|---------|--------------|--------|
| `qdrant` | Never restarted | Vector data in bind mount |
| `postgres` | Never restarted | Relational data in bind mount |
| `pgadmin` | Never restarted | Config in bind mount |
| `backend` | Rebuilt + restarted | Stateless — safe to restart |
| `nginx` | Restarted | Config reload only — instant |

The `--no-deps` flag ensures only `backend` and `nginx` restart.
Qdrant and Postgres stay running with zero downtime.
