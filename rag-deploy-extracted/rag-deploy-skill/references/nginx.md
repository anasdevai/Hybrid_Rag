# Nginx Config for RAG Deployment

## Full nginx.conf

```nginx
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log  /var/log/nginx/error.log;

    # Upload size — for /ingest PDF/DOCX uploads
    client_max_body_size 50M;

    # Gzip for React static assets
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;

    server {
        listen 80;
        server_name _;

        # ── React Frontend ──────────────────────────────────────
        location / {
            root /usr/share/nginx/html;
            try_files $uri $uri/ /index.html;
            
            # Cache static assets
            location ~* \.(js|css|png|jpg|ico|svg|woff2)$ {
                expires 30d;
                add_header Cache-Control "public, immutable";
            }
        }

        # ── FastAPI — General API ────────────────────────────────
        # Handles /query (slow — Gemini + reranker can take 10-30s)
        location /api/ {
            proxy_pass         http://backend:8000/;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_read_timeout 120s;     # CRITICAL: Gemini + reranker is slow
            proxy_connect_timeout 10s;
            proxy_send_timeout  30s;
        }

        # ── Webhook — returns 202 immediately ───────────────────
        location /api/webhook/ {
            proxy_pass         http://backend:8000/webhook/;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_read_timeout 30s;      # Fast — BackgroundTasks return 202
            proxy_connect_timeout 10s;
        }

        # ── Ingest — returns 202 immediately ────────────────────
        location /api/ingest/ {
            proxy_pass         http://backend:8000/ingest/;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_read_timeout 30s;      # Fast — BackgroundTasks return 202
            proxy_connect_timeout 10s;
            client_max_body_size 50M;    # Allow large PDF uploads
        }

        # ── Health check (used by Docker + monitoring) ──────────
        location /health {
            proxy_pass         http://backend:8000/health;
            proxy_read_timeout 5s;
        }
    }
}
```

## Timeout explanation

| Endpoint | Timeout | Reason |
|----------|---------|--------|
| `/api/` (query) | 120s | Qdrant search + BM25 + reranker + Gemini API call |
| `/api/webhook/` | 30s | FastAPI BackgroundTasks — 202 returned immediately |
| `/api/ingest/` | 30s | FastAPI BackgroundTasks — 202 returned immediately |
| `/health` | 5s | Should always be instant |

## Common Nginx errors

### 502 Bad Gateway
Backend container not ready. Check:
```bash
docker compose logs backend --tail=30
docker compose ps
```

### 413 Request Entity Too Large  
File upload too big. Increase `client_max_body_size` in both the `server` 
block AND the specific `location /api/ingest/` block.

### 504 Gateway Timeout
`proxy_read_timeout` too low. For `/api/` (query endpoint), 
set to at least 120s — Gemini API + reranker can take 20-40s on 4GB VPS.
