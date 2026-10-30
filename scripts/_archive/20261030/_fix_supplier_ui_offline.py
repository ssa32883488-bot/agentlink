"""Fix supplier UI showing agents offline."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c.open_sftp()
    sftp.put(str(ROOT / "ui/config_supplier_domain.yaml"), "/opt/agentlink/ui/config_supplier_domain.yaml")
    remote = "/tmp/fix_supplier_ui_offline.sh"
    script = r"""#!/bin/bash
set -e
cd /opt/agentlink
echo '== before config =='
grep api_base ui/config_supplier_domain.yaml || true
# ensure https + verify off
python3 - <<'PY'
from pathlib import Path
p = Path('ui/config_supplier_domain.yaml')
t = p.read_text(encoding='utf-8')
t = t.replace('http://127.0.0.1:8011', 'https://127.0.0.1:8011')
t = t.replace('http://127.0.0.1:8013', 'https://127.0.0.1:8013')
t = t.replace('http://127.0.0.1:8014', 'https://127.0.0.1:8014')
p.write_text(t, encoding='utf-8')
print('config rewritten')
PY
# ensure unit has UI_HTTPX_VERIFY=0 and correct ssl
CRT=/etc/agentlink/tls/server.crt
KEY=/etc/agentlink/tls/server.key
[ -f "$CRT" ] || { CRT=/opt/agentlink/certs/platform/supplier-a/server-cert.pem; KEY=/opt/agentlink/certs/platform/supplier-a/server-key.pem; }
cat >/etc/systemd/system/agentlink-ui-supplier.service <<EOF
[Unit]
Description=AgentLink UI ui-supplier
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
Environment=HOST=0.0.0.0
Environment=UI_PORT=8091
Environment=UI_HTTPX_VERIFY=0
Environment=AGENTLINK_UI_CONFIG=/opt/agentlink/ui/config_supplier_domain.yaml
EnvironmentFile=-/opt/agentlink/.env
ExecStart=/opt/agentlink/.venv/bin/python -m uvicorn ui.app:app --host 0.0.0.0 --port 8091 --ssl-certfile $CRT --ssl-keyfile $KEY
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/ui-supplier.log
StandardError=append:/var/log/agentlink/ui-supplier.log

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c agentlink-ui-supplier
sleep 4
echo '== services =='
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c agentlink-ui-supplier
echo '== agent health =='
curl -sk -o /dev/null -w 'a=%{http_code} ' https://127.0.0.1:8011/health
curl -sk -o /dev/null -w 'b=%{http_code} ' https://127.0.0.1:8013/health
curl -sk -o /dev/null -w 'c=%{http_code}\n' https://127.0.0.1:8014/health
echo '== ui agent health json =='
curl -sk https://127.0.0.1:8091/api/agents/supplier-a/health
echo
curl -sk https://127.0.0.1:8091/api/agents/supplier-b/health
echo
curl -sk https://127.0.0.1:8091/api/agents/supplier-c/health
echo
echo '== after config =='
grep api_base ui/config_supplier_domain.yaml
"""
    with sftp.file(remote, "w") as f:
        f.write(script)
    sftp.close()
    _, o, _ = c.exec_command(f"bash {remote}", timeout=90, get_pty=True)
    raw = o.read()
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.write(b"\n")
    c.close()


if __name__ == "__main__":
    main()
