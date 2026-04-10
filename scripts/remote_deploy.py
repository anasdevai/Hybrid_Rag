#!/usr/bin/env python3
"""Remote deployment script using paramiko SSH."""
import paramiko
import sys
import time

HOST = "65.21.244.158"
USER = "root"
PASS = "Cph181ko!!"
APP_DIR = "/opt/hybrid-rag"
REPO_URL = "https://github.com/anasdevai/Hybrid_Rag.git"

ENV_CONTENT = """GOOGLE_API_KEY=AIzaSyBIFut2fVK4izJbPfGMnNRmlZez1R1GM24
COLLECTION_NAME=hybrid_rag_docs
COLLECTION_SOPS=docs_sops
COLLECTION_DEVIATIONS=docs_deviations
COLLECTION_CAPAS=docs_capas
COLLECTION_DECISIONS=docs_decisions
COLLECTION_AUDITS=docs_audits
QDRANT_URL=https://057b3e75-8377-4008-8fed-20da94bd282c.sa-east-1-0.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6MGI0YjZhYjQtZGRjNi00YzhhLThiNWQtNDdlOGE0NDE3OWU3In0.IQqqnPEky62bFsjFEBrRSgLWLBNBoOyRID1c1hsKjfY
POSTGRES_USER=postgres
POSTGRES_PASSWORD=admin123
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=qdrant
JWT_SECRET_KEY=09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7
JWT_REFRESH_SECRET_KEY=fc2a1bb92b5168dbfae40a0bb1e19d7d457b01d360ad4ad6551bafb7a5a8e030
WEBHOOK_SECRET=my-custom-super-secret-key
HF_HOME=/app/models
TRANSFORMERS_CACHE=/app/models
"""

def run(client, cmd, timeout=300):
    print(f"\n>>> {cmd[:80]}...")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out:
        print(out[-2000:])  # last 2000 chars
    if err:
        print("STDERR:", err[-1000:])
    return out, err

def main():
    print(f"Connecting to {HOST}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=30)
    print("Connected!")

    # 1. Install Docker if not present
    run(client, "which docker || (curl -fsSL https://get.docker.com | sh && systemctl enable docker && systemctl start docker)", timeout=120)

    # 2. Install docker compose plugin if not present
    run(client, "docker compose version || apt-get install -y docker-compose-plugin", timeout=60)

    # 3. Create app directory and clone/pull repo
    run(client, f"mkdir -p {APP_DIR}")
    
    # Check if repo already cloned
    out, _ = run(client, f"test -d {APP_DIR}/.git && echo 'exists' || echo 'fresh'")
    if 'exists' in out:
        print("Repo exists, pulling latest...")
        run(client, f"cd {APP_DIR} && git fetch origin && git reset --hard origin/main && git pull origin main", timeout=60)
    else:
        print("Cloning repo...")
        run(client, f"git clone {REPO_URL} {APP_DIR}", timeout=120)

    # 4. Write .env file
    print("\n>>> Writing .env file...")
    sftp = client.open_sftp()
    with sftp.open(f"{APP_DIR}/.env", 'w') as f:
        f.write(ENV_CONTENT)
    sftp.close()
    print(".env written.")

    # 5. Create data directory for postgres volume
    run(client, f"mkdir -p {APP_DIR}/data/postgres")

    # 6. Build and start containers
    print("\n>>> Building and starting Docker containers (this may take 5-10 min on first run)...")
    run(client, f"cd {APP_DIR} && docker compose pull db 2>/dev/null || true", timeout=60)
    run(client, f"cd {APP_DIR} && docker compose build --no-cache backend", timeout=600)
    run(client, f"cd {APP_DIR} && docker compose up -d", timeout=120)

    # 7. Wait for backend to be healthy
    print("\n>>> Waiting for backend to become healthy...")
    for i in range(24):  # 2 min max
        time.sleep(5)
        out, _ = run(client, f"cd {APP_DIR} && docker compose ps --format json 2>/dev/null | python3 -c \"import sys,json; [print(s.get('Health','')) for s in [json.loads(l) for l in sys.stdin if l.strip()] if s.get('Service')=='backend']\" 2>/dev/null || docker inspect --format='{{{{.State.Health.Status}}}}' $(docker compose -f {APP_DIR}/docker-compose.yml ps -q backend) 2>/dev/null")
        if 'healthy' in out:
            print(f"Backend healthy after {(i+1)*5}s!")
            break
        print(f"  Waiting... ({(i+1)*5}s)")

    # 8. Final status
    run(client, f"cd {APP_DIR} && docker compose ps")
    run(client, "curl -s http://localhost/health || curl -s http://localhost:8000/health")

    print("\n=== Deployment complete! ===")
    print(f"App should be accessible at: http://{HOST}")
    client.close()

if __name__ == "__main__":
    main()
