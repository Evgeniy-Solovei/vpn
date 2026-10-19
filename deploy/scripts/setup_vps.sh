#!/bin/bash
# ==============================================================================
# VPN Live Dev - VPS Auto-setup & Kernel Network Optimization Script
# Target OS: Debian 12 / Ubuntu 22.04+ (Netherlands / Germany / Europe)
# ==============================================================================

set -e

echo "=========================================================="
echo "🚀 VPN Live Dev: Настройка сервера и оптимизация TCP BBR"
echo "=========================================================="

# 1. Update system packages
echo "📦 Обновление системных пакетов..."
apt update && apt upgrade -y
apt install -y curl wget git ufw iptables socat jq ca-certificates gnupg

# 2. Kernel optimization for high-throughput VPN (TCP BBR + Buffers)
echo "⚡ Включение TCP BBR и оптимизация сетевых буферов..."
cat <<EOF > /etc/sysctl.d/99-vpn-performance.conf
# TCP BBR Congestion Control
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr

# TCP Buffer sizes for high-bandwidth connections
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.core.rmem_default = 65536
net.core.wmem_default = 65536
net.ipv4.tcp_rmem = 4096 87380 67108864
net.ipv4.tcp_wmem = 4096 65536 67108864

# Network connection tuning
net.core.netdev_max_backlog = 100000
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.tcp_max_tw_buckets = 2000000
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 10
net.ipv4.tcp_slow_start_after_idle = 0
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF

sysctl --system

# 3. Setup Firewall (UFW)
echo "🛡️ Настройка файрвола (UFW)..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP / ACME
ufw allow 443/tcp     # HTTPS / VLESS Reality
ufw allow 2053/tcp    # 3X-UI Panel
ufw --force enable

# 4. Install Docker & Docker Compose if not present
if ! command -v docker &> /dev/null; then
    echo "🐳 Установка Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

echo "=========================================================="
echo "✅ Сервер оптимизирован!"
echo "BBR статус: $(sysctl net.ipv4.tcp_congestion_control)"
echo "Для развертывания проекта выполните: docker compose up -d --build"
echo "=========================================================="
