"""Ensure buyer (8090) + supplier (8091) UIs, open two browser tabs."""
from __future__ import annotations

import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER_HOST = "81.70.46.119"
SUPPLIER_HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

# 采购侧用域名（Let's Encrypt）；IP 访问会触发 ERR_CERT_COMMON_NAME_INVALID
BUYER_URL = "https://ashui.online:8090/"
SUPPLIER_PUBLIC = "https://39.105.20.113:8091/"  # 阿里云无域名，仅 IP
SUPPLIER_LOCAL = "https://127.0.0.1:18091/"


def _ssh(host: str, *, password: str | None = None) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        c.connect(host, username="root", password=password, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            host,
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def _run(c: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    return o.read().decode("utf-8", errors="replace")


def _http_ok(url: str, timeout: float = 8.0) -> bool:
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=timeout) as r:
            return 200 <= int(r.status) < 500
    except Exception:
        return False


def ensure_buyer() -> None:
    c = _ssh(BUYER_HOST)
    out = _run(
        c,
        "systemctl restart agentlink-ui-buyer; sleep 2; "
        "systemctl is-active agentlink-ui-buyer; "
        "curl -sk -o /dev/null -w 'ui=%{http_code}\\n' https://127.0.0.1:8090/",
    )
    print("buyer:", out.strip())
    c.close()


def ensure_supplier() -> None:
    c = _ssh(SUPPLIER_HOST, password=PW)
    # upload config
    sftp = c.open_sftp()
    sftp.put(str(ROOT / "ui/config_supplier_domain.yaml"), "/opt/agentlink/ui/config_supplier_domain.yaml")
    remote_sh = "/tmp/ensure_ui_supplier.sh"
    script = r"""#!/bin/bash
set -e
cd /opt/agentlink
mkdir -p /etc/agentlink /var/log/agentlink
# pick TLS materials
CRT=/etc/agentlink/tls/server.crt
KEY=/etc/agentlink/tls/server.key
if [ ! -f "$CRT" ]; then CRT=/etc/agentlink/tls/fullchain.pem; KEY=/etc/agentlink/tls/privkey.pem; fi
if [ ! -f "$CRT" ]; then CRT=/opt/agentlink/certs/platform/supplier-a/server-cert.pem; KEY=/opt/agentlink/certs/platform/supplier-a/server-key.pem; fi
echo "tls=$CRT"
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
systemctl enable agentlink-ui-supplier >/dev/null 2>&1 || true
systemctl restart agentlink-ui-supplier
sleep 3
systemctl is-active agentlink-ui-supplier
curl -sk -o /dev/null -w 'ui=%{http_code}\n' https://127.0.0.1:8091/
ss -lntp | grep 8091 || true
(firewall-cmd --permanent --add-port=8091/tcp; firewall-cmd --reload) >/dev/null 2>&1 || true
# aliyun security group may still block; local health is enough
"""
    with sftp.file(remote_sh, "w") as f:
        f.write(script)
    sftp.close()
    out = _run(c, f"bash {remote_sh}")
    print("supplier:", out.strip())
    c.close()


class _Tunnel:
    def __init__(self) -> None:
        self._stop = False
        self._client: paramiko.SSHClient | None = None

    def start(self) -> None:
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        for _ in range(30):
            if _http_ok(SUPPLIER_LOCAL, timeout=2):
                return
            # even if https handshake fails briefly, port may be open
            try:
                s = socket.create_connection(("127.0.0.1", 18091), timeout=1)
                s.close()
                time.sleep(0.5)
                return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("local tunnel 18091 not ready")

    def _loop(self) -> None:
        import select

        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(
            SUPPLIER_HOST,
            username="root",
            password=PW,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
        self._client = c
        transport = c.get_transport()
        assert transport is not None
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 18091))
        sock.listen(50)
        print("tunnel: 127.0.0.1:18091 -> supplier:8091", flush=True)
        while not self._stop:
            r, _, _ = select.select([sock], [], [], 1.0)
            if not r:
                continue
            client, addr = sock.accept()

            def handle(cli=client, a=addr):
                try:
                    chan = transport.open_channel("direct-tcpip", ("127.0.0.1", 8091), a)
                    while True:
                        rr, _, _ = select.select([cli, chan], [], [], 120)
                        if not rr:
                            break
                        if cli in rr:
                            data = cli.recv(65536)
                            if not data:
                                break
                            chan.sendall(data)
                        if chan in rr:
                            data = chan.recv(65536)
                            if not data:
                                break
                            cli.sendall(data)
                except Exception as exc:  # noqa: BLE001
                    print("tunnel err", exc, flush=True)
                finally:
                    try:
                        cli.close()
                    except Exception:
                        pass

            threading.Thread(target=handle, daemon=True).start()


def main() -> None:
    ensure_buyer()
    ensure_supplier()

    buyer_ok = _http_ok(BUYER_URL)
    print("buyer public ok:", buyer_ok)
    supplier_url = SUPPLIER_PUBLIC
    tunnel = None
    if _http_ok(SUPPLIER_PUBLIC):
        print("supplier public 8091 ok")
    else:
        print("supplier public 8091 blocked — starting SSH tunnel")
        tunnel = _Tunnel()
        tunnel.start()
        supplier_url = SUPPLIER_LOCAL

    print("open buyer:", BUYER_URL)
    print("open supplier:", supplier_url)
    webbrowser.open(BUYER_URL)
    time.sleep(0.8)
    webbrowser.open(supplier_url)

    if tunnel is not None:
        print("隧道需保持运行；本窗口将挂起约 2 小时（Ctrl+C 结束）")
        try:
            time.sleep(7200)
        except KeyboardInterrupt:
            print("stopped")


if __name__ == "__main__":
    main()
