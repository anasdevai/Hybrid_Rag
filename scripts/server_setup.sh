#!/bin/bash
# Run ONCE on fresh server: bash server_setup.sh
set -e

echo ">>> Installing Docker..."
curl -fsSL https://get.docker.com | sh
apt-get install -y docker-compose-plugin git

# Add 2GB swap (safety net for 4GB VPS)
echo ">>> Setting up swap..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    sysctl -p
    echo "    2GB swap created"
else
    echo "    Swap already exists"
fi

# Clone repo
echo ">>> Cloning repo..."
mkdir -p /opt/hybrid-rag
git clone https://github.com/sclera-ki/AI-Law-Firm-ChatBot.git /opt/hybrid-rag
cd /opt/hybrid-rag/Main

# Create data dirs
mkdir -p data/postgres

# Make scripts executable
chmod +x deploy.sh scripts/smoke_test.sh scripts/server_setup.sh

echo ""
echo "════════════════════════════════════════"
echo "  Server ready. Next steps:"
echo "  1. cd /opt/hybrid-rag/Main"
echo "  2. cp .env.example .env && nano .env"
echo "  3. docker compose up -d --build"
echo "  4. docker compose logs -f backend"
echo "════════════════════════════════════════"
