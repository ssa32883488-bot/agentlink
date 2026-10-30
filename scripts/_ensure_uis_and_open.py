"""Ensure buyer+supplier console UIs are up, then open in local browser."""
from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_UI = "https://81.70.46.119:8090/"
# 供应控制台在阿里云；若公网未放行 8091，可走本机端口转发后再开
SUPPLIER_UI_PUBLIC = "https://39.105.20.113:8091/"
SUPPLIER_UI_LOCAL = "https://127.0.0.1:18091/"


def ssh(host: str, *, password: str | None = None) -> paramiko.SSHClient:
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


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    return o.read().decode("utf-8", errors="replace")


def ensure_buyer_ui() -> None:
    c = ssh(BUYER)
    out = run(
        c,
        r"""
systemctl is-active agentlink-ui-buyer || true
curl -sk -o /dev/null -w 'ui=%{http_code}\n' https://127.0.0.1:8090/ || true
if ! systemctl is-active --quiet agentlink-ui-buyer; then
  systemctl restart agentlink-ui-buyer
  sleep 2
fi
systemctl is-active agentlink-ui-buyer
curl -sk -o /dev/null -w 'ui=%{http_code}\n' https://127.0.0.1:8090/
""",
    )
    print("==== buyer UI ====")
    print(out)
    c.close()


def ensure_supplier_ui() -> str:
    """Return preferred URL (public if reachable, else local tunnel hint)."""
    c = ssh(SUPPLIER, password=PW)
    # write remote ensure script to avoid $ expansion issues from Windows
    remote = "/tmp/ensure_supplier_ui.sh"
    script = r"""#!/bin/bash
set -e
cd /opt/agentlink
# unit may not exist yet — create minimal if missing
if [ ! -f /etc/systemd/system/agentlink-ui-supplier.service ]; then
  cat >/etc/systemd/system/agentlink-ui-supplier.service <<'EOF'
[Unit]
Description=AgentLink supplier console UI
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
Environment=HOST=0.0.0.0
Environment=UI_PORT=8091
Environment=UI_CONFIG=ui/config_supplier_domain.yaml
Environment=AGENTLINK_APP=ui.app:app
EnvironmentFile=-/opt/agentlink/.env
ExecStart=/opt/agentlink/.venv/bin/python /opt/agentlink/scripts/run_agent_https.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
fi
# ensure config exists
test -f ui/config_supplier_domain.yaml
systemctl enable agentlink-ui-supplier >/dev/null 2>&1 || true
systemctl restart agentlink-ui-supplier
sleep 3
systemctl is-active agentlink-ui-supplier
curl -sk -o /dev/null -w 'ui=%{http_code}\n' https://127.0.0.1:8091/ || true
ss -lntp | grep 8091 || true
# open firewall if firewalld present
(firewall-cmd --permanent --add-port=8091/tcp; firewall-cmd --reload) >/dev/null 2>&1 || true
"""
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(script)
    sftp.close()
    out = run(c, f"bash {remote}", timeout=120)
    print("==== supplier UI ====")
    print(out)
    c.close()

    # probe public
    import urllib.request
    import ssl

    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(SUPPLIER_UI_PUBLIC, context=ctx, timeout=8) as r:
            if r.status < 500:
                return SUPPLIER_UI_PUBLIC
    except Exception as exc:  # noqa: BLE001
        print("public 8091 not reachable:", exc)
    return "TUNNEL"


def start_local_tunnel() -> None:
    """ssh -L 18091:127.0.0.1:8091 root@39.105.20.113"""
    # start detached ssh tunnel
    cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-N",
        "-L",
        "18091:127.0.0.1:8091",
        f"root@{SUPPLIER}",
    ]
    # password auth via sshpass if available; else plink; else paramiko forward
    print("starting paramiko local port forward 18091 -> supplier:8091")
    # keep forward in background process via python
    subprocess.Popen(
        [
            "py",
            "-3",
            "-u",
            str(ROOT_SCRIPT),
        ],
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
    )


ROOT_SCRIPT = Path(__file__).with_name("_tunnel_supplier_ui.py")


def main() -> None:
    ensure_buyer_ui()
    mode = ensure_supplier_ui()
    supplier_url = SUPPLIER_UI_PUBLIC
    if mode == "TUNNEL":
        # write / start tunnel helper
        ROOT_SCRIPT.write_text(
            f"""
import os, time, socket, select
import paramiko
PW = os.environ.get('DEPLOY_PASSWORD', {PW!r})
HOST = {SUPPLIER!r}
LOCAL = 18091
REMOTE = 8091

def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username='root', password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    transport = c.get_transport()
    transport.request_port_forward('', 0)  # noop keepalive
    # reverse: local listen
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', LOCAL))
    sock.listen(5)
    print(f'tunnel ready https://127.0.0.1:{{LOCAL}}/', flush=True)
    while True:
        client, addr = sock.accept()
        chan = transport.open_channel('direct-tcpip', ('127.0.0.1', REMOTE), addr)
        while True:
            r, _, _ = select.select([client, chan], [], [])
            if client in r:
                data = client.recv(65536)
                if not data: break
                chan.send(data)
            if chan in r:
                data = chan.recv(65536)
                if not data: break
                client.send(data)
        chan.close(); client.close()

if __name__ == '__main__':
    main()
""",
            encoding="utf-8",
        )
        # simpler: use paramiko Transport forward in this process briefly via Thread
        import threading
        import socket
        import select

        def tunnel_loop():
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(SUPPLIER, username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
            transport = c.get_transport()
            assert transport is not None
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", 18091))
            sock.listen(20)
            print("tunnel listening on 18091", flush=True)
            while True:
                client, addr = sock.accept()

                def handle(cli=client, a=addr):
                    try:
                        chan = transport.open_channel("direct-tcpip", ("127.0.0.1", 8091), a)
                        while True:
                            r, _, _ = select.select([cli, chan], [], [], 60)
                            if not r:
                                break
                            if cli in r:
                                data = cli.recv(65536)
                                if not data:
                                    break
                                chan.send(data)
                            if chan in r:
                                data = chan.recv(65536)
                                if not data:
                                    break
                                cli.send(data)
                    except Exception as exc:  # noqa: BLE001
                        print("tunnel conn err", exc, flush=True)
                    finally:
                        try:
                            cli.close()
                        except Exception:
                            pass

                threading.Thread(target=handle, daemon=True).start()

        threading.Thread(target=tunnel_loop, daemon=True).start()
        import time

        time.sleep(1.5)
        supplier_url = SUPPLIER_UI_LOCAL

    print("opening:", BUYER_UI)
    print("opening:", supplier_url)
    webbrowser.open(BUYER_UI)
    webbrowser.open(supplier_url)
    if mode == "TUNNEL":
        print("tunnel thread running — keep this process alive 10 min")
        import time

        time.sleep(600)


if __name__ == "__main__":
    main()
