"""Wire supplier outbound AIP client certs + retest freight."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(SUPPLIER, username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)

    # Upload helper remote script to avoid local shell $ expansion
    remote_sh = "/tmp/fix_supplier_mtls.sh"
    script = r"""#!/bin/bash
set -e
cd /opt/agentlink
echo '== before =='
ls /etc/agentlink 2>/dev/null || true
for u in a b c; do
  f=/etc/agentlink/supplier-${u}.env
  mkdir -p /etc/agentlink
  touch "$f"
  # ensure client cert for outbound to logistics
  cert=/opt/agentlink/certs/platform/supplier-${u}/agent-cert.pem
  key=/opt/agentlink/certs/platform/supplier-${u}/agent-key.pem
  if [ ! -f "$cert" ]; then
    echo "missing $cert"
    ls /opt/agentlink/certs/platform/ || true
    continue
  fi
  grep -q '^AIP_CLIENT_CERT=' "$f" && sed -i "s|^AIP_CLIENT_CERT=.*|AIP_CLIENT_CERT=$cert|" "$f" || echo "AIP_CLIENT_CERT=$cert" >> "$f"
  grep -q '^AIP_CLIENT_KEY=' "$f" && sed -i "s|^AIP_CLIENT_KEY=.*|AIP_CLIENT_KEY=$key|" "$f" || echo "AIP_CLIENT_KEY=$key" >> "$f"
  grep -q '^AIP_TRUST_BUNDLE=' "$f" || echo 'AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle.pem' >> "$f"
  grep -q '^AIP_SSL_INSECURE=' "$f" || echo 'AIP_SSL_INSECURE=0' >> "$f"
  grep -q '^AIP_IDENTITY_BINDING=' "$f" && sed -i 's|^AIP_IDENTITY_BINDING=.*|AIP_IDENTITY_BINDING=0|' "$f" || echo 'AIP_IDENTITY_BINDING=0' >> "$f"
  grep -q '^LOGISTICS_RPC_URL=' "$f" || echo 'LOGISTICS_RPC_URL=https://81.70.46.119:8015/rpc' >> "$f"
  echo "---- supplier-$u.env"
  cat "$f"
done

# ensure systemd units load per-agent env (append if missing)
for u in a b c; do
  unit=/etc/systemd/system/agentlink-supplier-${u}.service
  if ! grep -q "supplier-${u}.env" "$unit"; then
    sed -i "/EnvironmentFile=-\/opt\/agentlink\/.env/a EnvironmentFile=-/etc/agentlink/supplier-${u}.env" "$unit" || true
  fi
  echo "---- unit $u"
  grep EnvironmentFile "$unit" || true
done

systemctl daemon-reload
systemctl reset-failed agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c || true
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 5
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
curl -sk -o /dev/null -w 'a=%{http_code} ' https://127.0.0.1:8011/health
curl -sk -o /dev/null -w 'b=%{http_code} ' https://127.0.0.1:8013/health
curl -sk -o /dev/null -w 'c=%{http_code}\n' https://127.0.0.1:8014/health
"""
    sftp = c.open_sftp()
    with sftp.file(remote_sh, "w") as f:
        f.write(script)
    sftp.close()
    _, o, _ = c.exec_command(f"bash {remote_sh}", timeout=90, get_pty=True)
    print(o.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
