#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.acme.sh:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
DOMAIN=moknobita.xyz
WWW=www.moknobita.xyz

source /root/.acme.sh/acme.sh.env 2>/dev/null || true
/root/.acme.sh/acme.sh --set-default-ca --server letsencrypt || true

echo "== stop frontend (:80/:443) =="
docker stop docker-frontend-1 || true
sleep 2
ss -lntp | grep -E ':80 |:443 ' || echo "80/443 free"

echo "== issue via TLS-ALPN-01 =="
set +e
/root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --alpn --force --server letsencrypt -k 2048
RC=$?
set -e

echo "== restore frontend =="
docker start docker-frontend-1 || true

if [ "$RC" -ne 0 ]; then
  echo "ALPN failed rc=$RC — try DNS manual next"
  exit "$RC"
fi

mkdir -p /etc/agentlink/tls
/root/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
  --fullchain-file /etc/agentlink/tls/fullchain.pem \
  --key-file /etc/agentlink/tls/privkey.pem \
  --reloadcmd "systemctl restart agentlink-supplier-a.service agentlink-supplier-b.service agentlink-supplier-c.service"
ln -sfn /etc/agentlink/tls/fullchain.pem /etc/agentlink/tls/server.crt
ln -sfn /etc/agentlink/tls/privkey.pem /etc/agentlink/tls/server.key
for u in agentlink-supplier-a.service agentlink-supplier-b.service agentlink-supplier-c.service; do
  f="/etc/systemd/system/${u}"
  [ -f "$f" ] || continue
  sed -i 's|--ssl-certfile [^ ]*|--ssl-certfile /etc/agentlink/tls/fullchain.pem|' "$f"
  sed -i 's|--ssl-keyfile [^ ]*|--ssl-keyfile /etc/agentlink/tls/privkey.pem|' "$f"
done
systemctl daemon-reload
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
openssl x509 -in /etc/agentlink/tls/fullchain.pem -noout -subject -issuer -dates
echo LE_SUPPLIER_OK
