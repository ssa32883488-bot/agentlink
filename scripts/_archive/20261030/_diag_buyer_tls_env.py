# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r"""
set +e
echo '=== systemd EnvironmentFile / Environment ==='
systemctl cat agentlink-buyer-a 2>/dev/null | grep -E 'Environment|EnvironmentFile' | head -40
echo '=== show AIP vars ==='
systemctl show agentlink-buyer-a -p Environment 2>/dev/null | tr ' ' '\n' | grep -E 'AIP_|SSL' || true
echo '=== drop-ins ==='
ls -la /etc/systemd/system/agentlink-buyer-a.service.d/ 2>/dev/null
for f in /etc/systemd/system/agentlink-buyer-a.service.d/*.conf /etc/agentlink/buyer-a.env /etc/agentlink/buyer.env; do
  [ -f "$f" ] || continue
  echo "--- $f ---"
  grep -E 'AIP_|SSL|CERT|TRUST' "$f" | head -40
done
echo '=== .env AIP ==='
grep -E '^AIP_' /opt/agentlink/.env | sed 's/\(KEY\|CERT\|BUNDLE\|PEM\)=.*/\1=***/'
echo '=== certs exist ==='
ls -la /opt/agentlink/certs/platform/buyer-a/ 2>/dev/null | head
ls -la /opt/agentlink/certs/platform/trust-bundle.pem 2>/dev/null
echo '=== quick openssl to supplier-a ==='
echo | timeout 8 openssl s_client -connect 39.105.20.113:8011 -servername 39.105.20.113 2>/dev/null | openssl x509 -noout -subject -issuer -dates 2>/dev/null | head
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(REMOTE, timeout=60, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
