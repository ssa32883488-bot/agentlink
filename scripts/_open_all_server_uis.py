# -*- coding: utf-8 -*-
"""Tunnel all 6 agent UIs to localhost and open in browser."""
from __future__ import annotations

import os
import select
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
TENCENT = "81.70.46.119"
ALIYUN = "39.105.20.113"

# (label, cloud, remote_port, local_port, scheme)
UIS = [
    ("buyer-a", "tencent", 8090, 18090, "https"),
    ("buyer-b", "tencent", 8092, 18092, "https"),
    ("logistics", "tencent", 8095, 18095, "https"),
    ("supplier-a", "aliyun", 8091, 18091, "http"),
    ("supplier-b", "aliyun", 8093, 18093, "http"),
    ("supplier-c", "aliyun", 8094, 18094, "http"),
]


def ssh(host: str, *, key: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = {
        "hostname": host,
        "username": "root",
        "timeout": 40,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if key:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def ensure_services() -> None:
    c = ssh(TENCENT, key=True)
    print(
        run(
            c,
            "systemctl restart agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; "
            "sleep 3; systemctl is-active agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; "
            "for p in 8090 8092 8095; do echo -n H:$p ; curl -sk -o /dev/null -w ' %{http_code}\\n' https://127.0.0.1:$p/; done",
        ),
        flush=True,
    )
    c.close()
    c2 = ssh(ALIYUN, key=False)
    print(
        run(
            c2,
            "systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; "
            "sleep 4; systemctl is-active agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; "
            "for p in 8091 8093 8094; do echo -n H:$p ; curl -sS -o /dev/null -w ' %{http_code}\\n' http://127.0.0.1:$p/ || echo fail; done",
        ),
        flush=True,
    )
    c2.close()


def _port_open(port: int) -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.4)
        s.close()
        return True
    except OSError:
        return False


def start_forwards(client: paramiko.SSHClient, pairs: list[tuple[int, int]]) -> None:
    transport = client.get_transport()
    assert transport is not None

    def listen(local: int, remote: int) -> None:
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", local))
        sock.listen(50)
        print(f"forward 127.0.0.1:{local} -> :{remote}", flush=True)
        while True:
            r, _, _ = select.select([sock], [], [], 1.0)
            if not r:
                continue
            cli, addr = sock.accept()

            def handle(c=cli, a=addr, rem=remote):
                try:
                    chan = transport.open_channel("direct-tcpip", ("127.0.0.1", rem), a)
                    while True:
                        rr, _, _ = select.select([c, chan], [], [], 120)
                        if not rr:
                            break
                        if c in rr:
                            data = c.recv(65536)
                            if not data:
                                break
                            chan.sendall(data)
                        if chan in rr:
                            data = chan.recv(65536)
                            if not data:
                                break
                            c.sendall(data)
                except Exception as exc:  # noqa: BLE001
                    print(f"fwd {local}->{rem} err {exc}", flush=True)
                finally:
                    try:
                        c.close()
                    except Exception:
                        pass

            threading.Thread(target=handle, daemon=True).start()

    for local, remote in pairs:
        threading.Thread(target=listen, args=(local, remote), daemon=True).start()

    deadline = time.time() + 12
    pending = {p[0] for p in pairs}
    while pending and time.time() < deadline:
        pending = {p for p in pending if not _port_open(p)}
        if pending:
            time.sleep(0.15)
    if pending:
        raise RuntimeError(f"local ports not ready: {sorted(pending)}")


def http_get_ok(url: str) -> bool:
    import ssl

    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=8) as r:
            return 200 <= int(r.status) < 500
    except Exception as exc:  # noqa: BLE001
        print("probe fail", url, exc, flush=True)
        return False


def main() -> None:
    print("==== ensure remote UI services ====", flush=True)
    ensure_services()

    t_pairs = [(loc, rem) for _, cloud, rem, loc, _ in UIS if cloud == "tencent"]
    a_pairs = [(loc, rem) for _, cloud, rem, loc, _ in UIS if cloud == "aliyun"]

    print("==== start tunnels ====", flush=True)
    ct = ssh(TENCENT, key=True)
    ca = ssh(ALIYUN, key=False)
    start_forwards(ct, t_pairs)
    start_forwards(ca, a_pairs)

    urls: list[tuple[str, str]] = []
    for name, _cloud, _rem, loc, scheme in UIS:
        url = f"{scheme}://127.0.0.1:{loc}/"
        ok = http_get_ok(url)
        print(f"{name} ok={ok} {url}", flush=True)
        urls.append((name, url))

    print("==== open browsers ====", flush=True)
    for name, url in urls:
        print(f"open {name}: {url}", flush=True)
        webbrowser.open(url)
        time.sleep(0.7)

    print("隧道保持运行约 2 小时（Ctrl+C 结束）", flush=True)
    try:
        time.sleep(7200)
    except KeyboardInterrupt:
        print("stopped", flush=True)
    finally:
        ct.close()
        ca.close()


if __name__ == "__main__":
    main()
