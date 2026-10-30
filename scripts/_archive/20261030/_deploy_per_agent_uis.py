"""Deploy 6 independent agent ERP consoles; retire aggregate UI units."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce/buyer_service.py",
    "commerce/buyer_routes.py",
    "commerce/chat_buyer_wit.py",
    "commerce/procurement_case.py",
    "commerce/seed.py",
    "agents/buyer_a/main.py",
    "agents/buyer_b/main.py",
    "ui/app.py",
    "ui/static/app.js",
    "ui/static/styles.css",
    "ui/static/index.html",
    "ui/config_buyer_a.yaml",
    "ui/config_buyer_b.yaml",
    "ui/config_logistics.yaml",
    "docs/agent_portals.md",
]

SUPPLIER_FILES = [
    "ui/app.py",
    "ui/static/app.js",
    "ui/static/styles.css",
    "ui/static/index.html",
    "ui/config_supplier_a.yaml",
    "ui/config_supplier_b.yaml",
    "ui/config_supplier_c.yaml",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = c.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> None:
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    sys.stdout.buffer.write(o.read() + b"\n")


def main() -> None:
    # —— Tencent: buyer-a/b + logistics UIs ——
    print("==== Tencent ====", flush=True)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(b, BUYER_FILES)
    run(
        b,
        r"""
set -e
cd /opt/agentlink
CRT=/etc/agentlink/tls/fullchain.pem
KEY=/etc/agentlink/tls/privkey.pem
[ -f "$CRT" ] || { CRT=/etc/agentlink/tls/server.crt; KEY=/etc/agentlink/tls/server.key; }

mk_ui() {
  local name="$1" port="$2" cfg="$3"
  cat >/etc/systemd/system/agentlink-ui-${name}.service <<EOF
[Unit]
Description=AgentLink UI ${name}
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
EnvironmentFile=-/opt/agentlink/.env
Environment=HOST=0.0.0.0
Environment=UI_PORT=${port}
Environment=UI_HTTPX_VERIFY=0
Environment=AGENTLINK_UI_CONFIG=/opt/agentlink/ui/${cfg}
ExecStart=/opt/agentlink/.venv/bin/python -m uvicorn ui.app:app --host 0.0.0.0 --port ${port} --ssl-certfile ${CRT} --ssl-keyfile ${KEY}
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/ui-${name}.log
StandardError=append:/var/log/agentlink/ui-${name}.log

[Install]
WantedBy=multi-user.target
EOF
}

mk_ui buyer-a 8090 config_buyer_a.yaml
mk_ui buyer-b 8092 config_buyer_b.yaml
mk_ui logistics 8095 config_logistics.yaml

# stop old aggregate buyer UI name if different
systemctl stop agentlink-ui-buyer 2>/dev/null || true
systemctl disable agentlink-ui-buyer 2>/dev/null || true

systemctl daemon-reload
# ensure buyer-a env
grep -q '^BUYER_AGENT_ID=' /etc/agentlink/buyer-a.env 2>/dev/null || true
mkdir -p /etc/agentlink
grep -q '^BUYER_AGENT_ID=' /etc/agentlink/buyer-a.env 2>/dev/null || echo 'BUYER_AGENT_ID=buyer-a' >> /etc/agentlink/buyer-a.env
grep -q '^BUYER_AGENT_ID=' /etc/agentlink/buyer-b.env 2>/dev/null || echo 'BUYER_AGENT_ID=buyer-b' >> /etc/agentlink/buyer-b.env

systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
systemctl enable --now agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics
systemctl restart agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics
sleep 4
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics
curl -sk -o /dev/null -w 'a=%{http_code} ' --resolve ashui.online:8090:127.0.0.1 https://ashui.online:8090/
curl -sk -o /dev/null -w 'b=%{http_code} ' --resolve ashui.online:8092:127.0.0.1 https://ashui.online:8092/
curl -sk -o /dev/null -w 'l=%{http_code}\n' --resolve ashui.online:8095:127.0.0.1 https://ashui.online:8095/
(firewall-cmd --permanent --add-port=8092/tcp --add-port=8095/tcp; firewall-cmd --reload) >/dev/null 2>&1 || true
""",
    )
    b.close()

    # —— Aliyun: supplier A/B/C UIs ——
    print("==== Aliyun ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, SUPPLIER_FILES)
    run(
        s,
        r"""
set -e
cd /opt/agentlink
CRT=/etc/agentlink/tls/server.crt
KEY=/etc/agentlink/tls/server.key
[ -f "$CRT" ] || { CRT=/opt/agentlink/certs/platform/supplier-a/server-cert.pem; KEY=/opt/agentlink/certs/platform/supplier-a/server-key.pem; }

mk_ui() {
  local name="$1" port="$2" cfg="$3"
  cat >/etc/systemd/system/agentlink-ui-${name}.service <<EOF
[Unit]
Description=AgentLink UI ${name}
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
EnvironmentFile=-/opt/agentlink/.env
Environment=HOST=0.0.0.0
Environment=UI_PORT=${port}
Environment=UI_HTTPX_VERIFY=0
Environment=AGENTLINK_UI_CONFIG=/opt/agentlink/ui/${cfg}
# 供应控制台按 IP 访问，使用明文 HTTP；后端 AIP 仍走 HTTPS（UI_HTTPX_VERIFY=0）
ExecStart=/opt/agentlink/.venv/bin/python -m uvicorn ui.app:app --host 0.0.0.0 --port ${port}
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/ui-${name}.log
StandardError=append:/var/log/agentlink/ui-${name}.log

[Install]
WantedBy=multi-user.target
EOF
}

mk_ui supplier-a 8091 config_supplier_a.yaml
mk_ui supplier-b 8093 config_supplier_b.yaml
mk_ui supplier-c 8094 config_supplier_c.yaml

systemctl stop agentlink-ui-supplier 2>/dev/null || true
systemctl disable agentlink-ui-supplier 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
sleep 4
systemctl is-active agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
curl -sS -o /dev/null -w 'sa=%{http_code} ' http://127.0.0.1:8091/
curl -sS -o /dev/null -w 'sb=%{http_code} ' http://127.0.0.1:8093/
curl -sS -o /dev/null -w 'sc=%{http_code}\n' http://127.0.0.1:8094/
(firewall-cmd --permanent --add-port=8093/tcp --add-port=8094/tcp; firewall-cmd --reload) >/dev/null 2>&1 || true
""",
    )
    s.close()
    print("DEPLOY_PER_AGENT_UIS_DONE", flush=True)
    print(open(ROOT / "docs/agent_portals.md", encoding="utf-8").read())


if __name__ == "__main__":
    main()
