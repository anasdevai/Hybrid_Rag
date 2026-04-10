#!/usr/bin/env python3
"""Deploy rag-chatbot service to server."""
import paramiko, time

HOST = "65.21.244.158"
USER = "root"
PASS = "Cph181ko!!"
APP_DIR = "/opt/hybrid-rag"

def run(client, cmd, timeout=300):
    print(f"\n>>> {cmd[:100]}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out: print(out[-3000:])
    if err: print("ERR:", err[-500:])
    return out

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=30)
    print("Connected!")

    # Pull latest code
    run(client, f"cd {APP_DIR} && git pull origin main", timeout=60)

    # Build rag-chatbot image
    print("\n>>> Building rag-chatbot image (5-10 min first time)...")
    run(client, f"cd {APP_DIR} && docker compose build rag-chatbot", timeout=600)

    # Start/restart rag-chatbot and nginx
    run(client, f"cd {APP_DIR} && docker compose up -d --no-deps rag-chatbot nginx", timeout=60)

    # Wait for healthy
    print("\n>>> Waiting for rag-chatbot to be healthy...")
    for i in range(24):
        time.sleep(10)
        out = run(client, f"docker inspect --format='{{{{.State.Health.Status}}}}' $(cd {APP_DIR} && docker compose ps -q rag-chatbot) 2>/dev/null")
        if 'healthy' in out:
            print(f"Healthy after {(i+1)*10}s!")
            break
        print(f"  Waiting... ({(i+1)*10}s) status: {out.strip()}")

    # Smoke test
    run(client, "curl -s http://localhost/rag/health")
    run(client, f"cd {APP_DIR} && docker compose ps")

    print("\n=== rag-chatbot deployed! ===")
    print("Endpoints:")
    print("  POST http://65.21.244.158/rag/query")
    print("  POST http://65.21.244.158/rag/query/smart")
    print("  GET  http://65.21.244.158/rag/health")
    client.close()

if __name__ == "__main__":
    main()
