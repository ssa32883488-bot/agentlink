#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.acme.sh:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
EMAIL="${1:-3572962849@qq.com}"
DOMAIN=moknobita.xyz
WWW=www.moknobita.xyz

if [ ! -f /root/.acme.sh/acme.sh ]; then
  cd /root/acme.sh && ./acme.sh --install -m "$EMAIL"
fi
# shellcheck disable=SC1091
source /root/.acme.sh/acme.sh.env 2>/dev/null || true
/root/.acme.sh/acme.sh --set-default-ca --server letsencrypt || true

echo "== stop frontend occupying :80 =="
docker stop docker-frontend-1 || true
sleep 2
ss -lntp | grep ':80 ' || echo "port80_free"

echo "== issue LE =="
set +e
/root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --force --server letsencrypt -k 2048
RC=$?
set -e

echo "== start frontend =="
docker start docker-frontend-1 || true

if [ "$RC" -ne 0 ]; then
  echo "LE failed rc=$RC"
  exit "$RC"
fi

mkdir -p /etc/agentlink/tls
/root/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
  --fullchain-file /etc/agentlink/tls/fullchain.pem \
  --key-file /etc/agentlink/tls/privkey.pem \
  --reloadcmd "systemctl restart agentlink-supplier-a.service agentlink-supplier-b.service agentlink-supplier-c.service"

ln -sfn /etc/agentlink/tls/fullchain.pem /etc/agentlink/tls/server.crt
ln -sfn /etc/agentlink/tls/privkey.pem /etc/agentlink/tls/server.key
chmod 600 /etc/agentlink/tls/privkey.pem
chmod 644 /etc/agentlink/tls/fullchain.pem

for u in agentlink-supplier-a.service agentlink-supplier-b.service agentlink-supplier-c.service; do
  f="/etc/systemd/system/${u}"
  [ -f "$f" ] || continue
  sed -i 's|--ssl-certfile [^ ]*|--ssl-certfile /etc/agentlink/tls/fullchain.pem|' "$f"
  sed -i 's|--ssl-keyfile [^ ]*|--ssl-keyfile /etc/agentlink/tls/privkey.pem|' "$f"
done
systemctl daemon-reload
systemctl restart agentlink-supplier-a.service agentlink-supplier-b.service agentlink-supplier-c.service
sleep 2
openssl x509 -in /etc/agentlink/tls/fullchain.pem -noout -subject -issuer -dates
echo LE_SUPPLIER_OK
