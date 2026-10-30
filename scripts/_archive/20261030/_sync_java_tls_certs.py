# -*- coding: utf-8 -*-
"""Sync platform supplier certs into Java SSL_CERT paths and restart."""
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

CMD = r"""
set -e
for role in supplier-a supplier-b supplier-c; do
  src=/opt/agentlink/certs/platform/$role
  dst=/etc/agentlink/tls/aic/$role
  mkdir -p "$dst"
  echo "=== $role before ==="
  [ -f "$dst/server.crt" ] && openssl x509 -in "$dst/server.crt" -noout -subject || echo 'no old crt'
  # Java SSL uses server.crt/key; keep agent certs too if present
  cp -a "$src/server-cert.pem" "$dst/server.crt"
  cp -a "$src/server-key.pem" "$dst/server.key"
  if [ -f "$src/agent-cert.pem" ]; then
    cp -a "$src/agent-cert.pem" "$dst/agent.crt" 2>/dev/null || true
    cp -a "$src/agent-key.pem" "$dst/agent.key" 2>/dev/null || true
  fi
  chmod 644 "$dst/server.crt"
  chmod 600 "$dst/server.key"
  echo "=== $role after ==="
  openssl x509 -in "$dst/server.crt" -noout -subject
done
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 5
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
echo '=== live Java TLS CN ==='
for port in 8011 8013 8014; do
  echo -- $port --
  echo | timeout 8 openssl s_client -connect 127.0.0.1:$port 2>/dev/null | openssl x509 -noout -subject || echo FAIL
done
"""


def main() -> None:
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = s.exec_command(CMD, timeout=90)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    s.close()


if __name__ == "__main__":
    main()
