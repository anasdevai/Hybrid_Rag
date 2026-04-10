"""SSH deploy helper — run locally only, not committed."""
import paramiko, sys, time

HOST = "65.21.244.158"
USER = "root"
PASS = "Cph181ko!!"

def run(client, label, cmd, timeout=300):
    print(f">>> {label}...")
    transport = client.get_transport()
    chan = transport.open_session()
    chan.get_pty()
    chan.exec_command(cmd)
    buf = b""
    deadline = time.time() + timeout
    while True:
        if chan.recv_ready():
            chunk = chan.recv(4096)
            if not chunk:
                break
            buf += chunk
            # print live output
            try:
                lines = buf.decode(errors="replace")
                print(lines[-1000:] if len(lines) > 1000 else lines, end="", flush=True)
                buf = b""
            except:
                pass
        if chan.exit_status_ready():
            break
        if time.time() > deadline:
            print(f"\n  [timeout after {timeout}s]")
            break
        time.sleep(0.3)
    code = chan.recv_exit_status()
    print(f"\n  [exit {code}]\n")
    return code

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print(f"Connecting to {HOST}...")
client.connect(HOST, username=USER, password=PASS, timeout=30)
print("Connected.\n")

# Clone / pull repo
run(client, "Cloning repo", """
if [ -d /opt/hybrid-rag/.git ]; then
  cd /opt/hybrid-rag && git pull origin main
else
  git clone https://github.com/sclera-ki/AI-Law-Firm-ChatBot.git /opt/hybrid-rag
fi
""", timeout=120)

# Data dirs + permissions
run(client, "Creating dirs + permissions", """
mkdir -p /opt/hybrid-rag/Main/data/postgres
chmod +x /opt/hybrid-rag/Main/deploy.sh
chmod +x /opt/hybrid-rag/Main/scripts/smoke_test.sh
chmod +x /opt/hybrid-rag/Main/scripts/server_setup.sh
echo 'Done'
""")

# Check .env
run(client, "Checking .env", """
if [ -f /opt/hybrid-rag/Main/.env ]; then
  echo '.env EXISTS'
  grep -v 'KEY\|PASSWORD\|SECRET' /opt/hybrid-rag/Main/.env | head -10
else
  echo '.env MISSING'
fi
""")

# Show what is in /opt/hybrid-rag
run(client, "Listing /opt/hybrid-rag/Main", "ls -la /opt/hybrid-rag/Main/")

client.close()
print("\nServer setup complete.")
