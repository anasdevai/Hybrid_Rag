import paramiko

HOST = "65.21.244.158"
USER = "root"
PASS = "Cph181ko!!"

def run(client, cmd):
    _, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out: print(out)
    if err: print("ERR:", err)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS)

run(client, "cd /opt/hybrid-rag && docker compose logs rag-chatbot --tail=50")
client.close()
