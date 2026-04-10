import paramiko, time

HOST = "65.21.244.158"
USER = "root"
PASS = "Cph181ko!!"
APP_DIR = "/opt/hybrid-rag"

def run(client, cmd, timeout=600):
    print(f"\n>>> {cmd[:100]}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out: print(out[-3000:])
    if err: print("ERR:", err[-500:])
    return out

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS)
print("Connected!")

# Pull latest
run(client, f"cd {APP_DIR} && git pull origin main")

# Force no-cache rebuild
run(client, f"cd {APP_DIR} && docker compose build --no-cache rag-chatbot", timeout=700)

# Stop old container, start fresh
run(client, f"cd {APP_DIR} && docker compose stop rag-chatbot && docker compose rm -f rag-chatbot")
run(client, f"cd {APP_DIR} && docker compose up -d rag-chatbot", timeout=60)

# Wait and check logs
print("\nWaiting 30s for startup...")
time.sleep(30)
run(client, f"cd {APP_DIR} && docker compose logs rag-chatbot --tail=30")
run(client, f"cd {APP_DIR} && docker compose ps")

client.close()
