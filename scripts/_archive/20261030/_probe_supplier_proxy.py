# -*- coding: utf-8 -*-
"""Find reverse-proxy TLS termination for supplier ports 8011/8013/8014."""
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

CMD = r"""
echo "=== listeners ==="
ss -lntp | grep -E ':8011|:8013|:8014|:18011|:18013|:18014' || true
echo "=== nginx ==="
ls /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null
grep -RInE '8011|8013|8014|ssl_certificate|supplier' /etc/nginx 2>/dev/null | head -80
echo "=== caddy ==="
ls /etc/caddy 2>/dev/null; cat /etc/caddy/Caddyfile 2>/dev/null | head -80
echo "=== haproxy ==="
grep -nE '8011|8013|8014|crt|bind' /etc/haproxy/haproxy.cfg 2>/dev/null | head -40
echo "=== agentlink nginx/proxy configs ==="
find /opt/agentlink -maxdepth 3 -type f \( -name '*nginx*' -o -name '*proxy*' -o -name '*caddy*' \) 2>/dev/null
grep -RInE 'ssl_certificate|8011|18011' /opt/agentlink/deploy /opt/agentlink/ops /opt/agentlink/config 2>/dev/null | head -60
echo "=== systemd units mentioning 8011 ==="
grep -RInE '8011|18011|nginx|proxy' /etc/systemd/system/agentlink* 2>/dev/null | head -40
echo "=== live CN via 18011 and 8011 ==="
for addr in 127.0.0.1:18011 127.0.0.1:8011; do
  echo "-- $addr --"
  echo | timeout 5 openssl s_client -connect "$addr" 2>/dev/null | openssl x509 -noout -subject 2>/dev/null || echo FAIL_OR_PLAIN
done
"""


def main() -> None:
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = s.exec_command(CMD, timeout=60)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    s.close()


if __name__ == "__main__":
    main()
