# -*- coding: utf-8 -*-
"""Probe which CN supplier HTTPS ports actually present."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

ALIYUN = r"""
echo "=== file certs ==="
for role in supplier-a supplier-b supplier-c; do
  d=/opt/agentlink/certs/platform/$role
  echo "-- $role --"
  for f in agent-cert.pem server-cert.pem fullchain.pem cert.pem; do
    [ -f "$d/$f" ] || continue
    cn=$(openssl x509 -in "$d/$f" -noout -subject 2>/dev/null | sed -n 's/.*CN *= *\([^,]*\).*/\1/p' | tr -d ' ')
    echo "  $f => $cn"
  done
done
echo "=== systemd EnvironmentFile / unit certs ==="
for u in agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; do
  echo "-- $u --"
  systemctl show "$u" -p EnvironmentFiles -p FragmentPath 2>/dev/null | head -5
  envf=$(systemctl show "$u" -p EnvironmentFiles --value 2>/dev/null | head -1 | awk '{print $1}' | tr -d ' ')
  [ -n "$envf" ] && [ -f "$envf" ] && grep -E 'CERT|PEM|SSL|AIC|TLS' "$envf" | head -20
done
echo "=== live TLS CN on ports ==="
python3 - <<'PY'
import ssl, socket
for port in (8011, 8013, 8014):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with ctx.wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=5), server_hostname="127.0.0.1") as s:
            cert = s.getpeercert(binary_form=True)
        import subprocess, tempfile, os
        path = f"/tmp/peer-{port}.der"
        open(path, "wb").write(cert)
        out = subprocess.check_output(["openssl", "x509", "-inform", "DER", "-in", path, "-noout", "-subject"], text=True)
        print(port, out.strip())
    except Exception as e:
        print(port, "ERR", e)
PY
echo "=== supplier-a env AIC ==="
grep -E 'SUPPLIER_A_AIC|AIP_|SSL_|CERT' /etc/agentlink/supplier-a.env /opt/agentlink/.env 2>/dev/null | head -40
"""

TENCENT = r"""
echo "=== buyer expects ==="
grep -E 'SUPPLIER_[ABC]_AIC' /etc/agentlink/buyer-a.env /opt/agentlink/.env 2>/dev/null | sort -u
echo "=== extract from remote via openssl s_client ==="
for port in 8011 8013 8014; do
  echo "-- 39.105.20.113:$port --"
  echo | timeout 8 openssl s_client -connect 39.105.20.113:$port -servername 39.105.20.113 2>/dev/null \
    | openssl x509 -noout -subject 2>/dev/null || echo FAIL
done
"""


def main() -> None:
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = s.exec_command(ALIYUN, timeout=60)
    print("ALIYUN\n", (o.read() + e.read()).decode("utf-8", "replace"))
    s.close()

    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = b.exec_command(TENCENT, timeout=60)
    print("TENCENT\n", (o.read() + e.read()).decode("utf-8", "replace"))
    b.close()


if __name__ == "__main__":
    main()
