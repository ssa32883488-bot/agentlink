#!/usr/bin/env bash
set -euo pipefail
DOMAIN="$1"
WWW="$2"
EMAIL="$3"
SERVICES="$4"
STOP80="$5"
START80="$6"

export PATH="$HOME/.acme.sh:/root/.acme.sh:$HOME/.local/bin:/usr/local/bin:$PATH"
mkdir -p /etc/agentlink/tls /var/log/agentlink

# 国内机访问 get.acme.sh 常超时：优先 gitee 克隆安装
if [ ! -f /root/.acme.sh/acme.sh ]; then
  if [ ! -f /root/acme.sh/acme.sh ]; then
    dnf install -y git >/dev/null 2>&1 || yum install -y git >/dev/null 2>&1 || true
    git clone --depth 1 https://gitee.com/neilpang/acme.sh.git /root/acme.sh
  fi
  cd /root/acme.sh && ./acme.sh --install -m "$EMAIL"
fi
# shellcheck disable=SC1091
source /root/.acme.sh/acme.sh.env 2>/dev/null || true
export PATH="/root/.acme.sh:$PATH"

# 使用 Let's Encrypt 正式 CA
/root/.acme.sh/acme.sh --set-default-ca --server letsencrypt || true

echo "== freeing :80 for HTTP-01 =="
bash -c "$STOP80"
sleep 2
ss -lntp | grep ':80 ' || echo "port 80 free"

echo "== issuing cert for $DOMAIN =="
# 已存在则 force 续签/重签
if [ -d "/root/.acme.sh/${DOMAIN}_ecc" ] || [ -d "/root/.acme.sh/${DOMAIN}" ]; then
  /root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --force --server letsencrypt || \
  /root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --force --server letsencrypt -k 2048
else
  /root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --server letsencrypt || \
  /root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --server letsencrypt -k 2048
fi

echo "== restore :80 service =="
bash -c "$START80" || true

RELOAD="systemctl restart $SERVICES"
/root/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
  --fullchain-file /etc/agentlink/tls/fullchain.pem \
  --key-file /etc/agentlink/tls/privkey.pem \
  --reloadcmd "$RELOAD"

chmod 600 /etc/agentlink/tls/privkey.pem
chmod 644 /etc/agentlink/tls/fullchain.pem
# 兼容旧单元名
ln -sfn /etc/agentlink/tls/fullchain.pem /etc/agentlink/tls/server.crt
ln -sfn /etc/agentlink/tls/privkey.pem /etc/agentlink/tls/server.key

# 把 systemd 单元的证书路径切到 LE 文件（若仍指向旧路径则替换）
for u in $SERVICES; do
  f="/etc/systemd/system/${u}"
  if [ -f "$f" ]; then
    sed -i 's|--ssl-certfile [^ ]*|--ssl-certfile /etc/agentlink/tls/fullchain.pem|' "$f"
    sed -i 's|--ssl-keyfile [^ ]*|--ssl-keyfile /etc/agentlink/tls/privkey.pem|' "$f"
  fi
done
systemctl daemon-reload
systemctl restart $SERVICES
sleep 2
ss -lntp | grep -E '8010|8011|8012|8013|8014|8015' || true
openssl x509 -in /etc/agentlink/tls/fullchain.pem -noout -subject -issuer -dates | head -20
echo "LE_OK $DOMAIN"
