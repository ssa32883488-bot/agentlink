# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    cmd = r"""
set +e
for u in a b c; do
  echo "=== supplier-$u unit ==="
  systemctl cat agentlink-supplier-$u 2>/dev/null | head -80
  echo "=== supplier-$u.env ==="
  cat /etc/agentlink/supplier-$u.env 2>/dev/null || true
done
echo '=== openssl subjects ==='
for p in 8011 8013 8014; do
  echo "--- :$p ---"
  echo | timeout 6 openssl s_client -connect 127.0.0.1:$p 2>/dev/null | openssl x509 -noout -subject -issuer 2>/dev/null
done
echo '=== platform server cert subject ==='
openssl x509 -in /opt/agentlink/certs/platform/supplier-a/server-cert.pem -noout -subject -issuer 2>/dev/null
openssl x509 -in /etc/agentlink/tls/server.crt -noout -subject -issuer 2>/dev/null
"""
    _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
