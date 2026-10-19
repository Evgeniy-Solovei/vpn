#!/bin/bash
# ==============================================================================
# VPN live-dev - 1-Click New Node Setup Script (VLESS + Reality + XTLS Vision)
# Supported OS: Ubuntu 22.04 / 24.04, Debian 12
# Usage on fresh VPS: bash add_vpn_node.sh
# ==============================================================================

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}================================================================${NC}"
echo -e "${GREEN}🚀 VPN live-dev — Автоматическая установка новой VPN-ноды${NC}"
echo -e "${CYAN}================================================================${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}❌ Запустите скрипт от имени root (sudo -i)${NC}"
  exit 1
fi

# Detect Public IP
SERVER_IP=$(curl -s4 https://api.ipify.org || curl -s4 https://ifconfig.me || hostname -I | awk '{print $1}')
echo -e "📍 Внешний IP сервера: ${YELLOW}${SERVER_IP}${NC}"

# 1. Update and install prerequisites
echo -e "\n📦 ${CYAN}[1/5] Установка зависимостей (curl, jq, openssl, socat, ufw)...${NC}"
apt-get update -qq
apt-get install -y -qq curl jq openssl socat ufw > /dev/null 2>&1

# 2. Kernel optimization & TCP BBR
echo -e "⚡ ${CYAN}[2/5] Включение TCP BBR и оптимизация буферов...${NC}"
cat <<EOF > /etc/sysctl.d/99-vpn-bbr.conf
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.ipv4.tcp_rmem = 4096 87380 67108864
net.ipv4.tcp_wmem = 4096 65536 67108864
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
sysctl -p /etc/sysctl.d/99-vpn-bbr.conf > /dev/null 2>&1 || sysctl --system > /dev/null 2>&1

# 3. Install official Xray-core
echo -e "📦 ${CYAN}[3/5] Установка официального ядра Xray-core...${NC}"
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install > /dev/null 2>&1

# 4. Generate Reality Keypair and Short ID
echo -e "🔑 ${CYAN}[4/5] Генерация ключей Reality (X25519)...${NC}"
KEYS=$(xray x25519)
PRIVATE_KEY=$(echo "$KEYS" | grep "Private key" | awk '{print $3}')
PUBLIC_KEY=$(echo "$KEYS" | grep "Public key" | awk '{print $3}')
SHORT_ID=$(openssl rand -hex 8)
SNI_DOMAIN="www.microsoft.com"
PORT=443

# 5. Write Xray configuration
echo -e "⚙️ ${CYAN}[5/5] Создание конфигурации /usr/local/etc/xray/config.json...${NC}"
cat <<EOF > /usr/local/etc/xray/config.json
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "port": ${PORT},
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none",
        "fallbacks": []
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "${SNI_DOMAIN}:443",
          "xver": 0,
          "serverNames": [
            "${SNI_DOMAIN}",
            "azure.microsoft.com"
          ],
          "privateKey": "${PRIVATE_KEY}",
          "shortIds": [
            "${SHORT_ID}"
          ]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls", "quic"]
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "tag": "direct"
    },
    {
      "protocol": "blackhole",
      "tag": "block"
    }
  ]
}
EOF

# Open firewall ports
if command -v ufw > /dev/null 2>&1; then
  ufw allow 22/tcp > /dev/null 2>&1 || true
  ufw allow ${PORT}/tcp > /dev/null 2>&1 || true
fi

# Restart and enable service
systemctl daemon-reload
systemctl enable xray > /dev/null 2>&1
systemctl restart xray

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}🎉 НОВАЯ НОДА УСПЕШНО НАСТРОЕНА И ЗАПУЩЕНА!${NC}"
echo -e "${GREEN}================================================================${NC}\n"
echo -e "Вставьте эти параметры в панель управления:"
echo -e "🌐 ${CYAN}http://vpn.live-dev.by/admin/vpn/vpnserver/add/${NC}\n"
echo -e "┌────────────────────────┬──────────────────────────────────────────────┐"
echo -e "│ Поле в админке         │ Значение                                     │"
echo -e "├────────────────────────┼──────────────────────────────────────────────┤"
echo -e "│ IP сервера             │ ${YELLOW}${SERVER_IP}${NC}"
echo -e "│ Порт                   │ ${YELLOW}${PORT}${NC}"
echo -e "│ SNI (Маскировка)       │ ${YELLOW}${SNI_DOMAIN}${NC}"
echo -e "│ Reality Public Key     │ ${YELLOW}${PUBLIC_KEY}${NC}"
echo -e "│ Reality Short ID       │ ${YELLOW}${SHORT_ID}${NC}"
echo -e "│ Канал                  │ ${YELLOW}1 Gbps • Безлимит${NC}"
echo -e "└────────────────────────┴──────────────────────────────────────────────┘\n"
echo -e "${CYAN}💡 Совет: Код страны и город укажите в соответствии с локацией VPS (например FI / Хельсинки или NL / Амстердам).${NC}"
echo -e "${CYAN}Система автоматически подтянет флаг страны и добавит ноду в выбор клиентов!${NC}\n"
