# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
REMOTE = r"""
set -e
systemctl cat agentlink-ui-buyer-a | sed -n '1,50p'
echo ===PORTS===
ss -lntp | grep -E '80[0-9]{2}|81[0-9]{2}' || true
echo ===CURL===
for p in 8090 8088 8089 8100 8091 8000; do
  code=$(curl -s -o /tmp/u$p.html -w '%{http_code}' --max-time 3 http://127.0.0.1:$p/ || echo fail)
  echo "port_$p=$code"
  if grep -q auctionWatch /tmp/u$p.html 2>/dev/null; then echo "FOUND_HTML_$p"; fi
  n=$(curl -s --max-time 3 "http://127.0.0.1:$p/static/app.js" | grep -c renderAuctionWatch || true)
  echo "js_hits_$p=$n"
done
echo ===HTTPS===
for p in 8090 8443; do
  code=$(curl -sk -o /tmp/hs$p.html -w '%{http_code}' --max-time 3 https://127.0.0.1:$p/ || echo fail)
  echo "https_$p=$code"
  if grep -q auctionWatch /tmp/hs$p.html 2>/dev/null; then echo "FOUND_HTTPS_$p"; fi
  n=$(curl -sk --max-time 3 "https://127.0.0.1:$p/static/app.js" | grep -c renderAuctionWatch || true)
  echo "https_js_$p=$n"
done
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
    _, o, e = c.exec_command(REMOTE, timeout=90)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
