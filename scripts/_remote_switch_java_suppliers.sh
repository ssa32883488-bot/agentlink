#!/bin/bash
set -euo pipefail

if [ -f /etc/agentlink/tls/fullchain.pem ] && [ -f /etc/agentlink/tls/privkey.pem ]; then
  CRT=/etc/agentlink/tls/fullchain.pem
  KEY=/etc/agentlink/tls/privkey.pem
elif [ -f /etc/agentlink/tls/server.crt ] && [ -f /etc/agentlink/tls/server.key ]; then
  CRT=/etc/agentlink/tls/server.crt
  KEY=/etc/agentlink/tls/server.key
else
  echo "NO_TLS"
  exit 1
fi

JAVA_BIN="$(command -v java)"
if [ -z "$JAVA_BIN" ]; then
  echo "java missing"
  exit 1
fi
echo "JAVA=$JAVA_BIN TLS=$CRT"

write_java_unit() {
  local name="$1"
  local port="$2"
  cat > "/etc/systemd/system/agentlink-${name}.service" <<EOF
[Unit]
Description=AgentLink ${name} (Java HTTPS)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
Environment=AIP_IDENTITY_BINDING=0
Environment=AIP_SSL_INSECURE=1
Environment=PORT=${port}
Environment=SSL_ENABLED=true
Environment=SSL_CERT=file:${CRT}
Environment=SSL_KEY=file:${KEY}
EnvironmentFile=-/opt/agentlink/.env
EnvironmentFile=-/etc/agentlink/${name}.env
ExecStart=${JAVA_BIN} -jar /opt/agentlink/java-suppliers/${name}.jar
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/${name}.log
StandardError=append:/var/log/agentlink/${name}.log

[Install]
WantedBy=multi-user.target
EOF
}

mkdir -p /var/log/agentlink
# truncate old python logs so we see java boot clearly
: > /var/log/agentlink/supplier-a.log
: > /var/log/agentlink/supplier-b.log
: > /var/log/agentlink/supplier-c.log

systemctl stop agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c || true
write_java_unit supplier-a 8011
write_java_unit supplier-b 8013
write_java_unit supplier-c 8014
systemctl daemon-reload
systemctl enable agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
# Spring Boot cold start ~45s on this host
for i in $(seq 1 60); do
  if curl -skf https://127.0.0.1:8011/health >/dev/null \
    && curl -skf https://127.0.0.1:8013/health >/dev/null \
    && curl -skf https://127.0.0.1:8014/health >/dev/null; then
    break
  fi
  sleep 2
done
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
echo "--- health ---"
curl -sk https://127.0.0.1:8011/health; echo
curl -sk https://127.0.0.1:8013/health; echo
curl -sk https://127.0.0.1:8014/health; echo
echo "--- unit ---"
systemctl cat agentlink-supplier-a | head -30
echo "--- log a ---"
tail -n 50 /var/log/agentlink/supplier-a.log || true
