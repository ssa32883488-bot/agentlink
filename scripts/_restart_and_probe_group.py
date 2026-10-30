# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def connect(host: str, *, pem: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    t = c.get_transport()
    if t:
        t.set_keepalive(15)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    chunks: list[bytes] = []
    deadline = time.time() + timeout
    while True:
        if o.channel.recv_ready():
            chunks.append(o.channel.recv(4096))
        if o.channel.exit_status_ready() and not o.channel.recv_ready():
            break
        if time.time() > deadline:
            break
        time.sleep(0.2)
    try:
        while o.channel.recv_ready():
            chunks.append(o.channel.recv(4096))
    except Exception:
        pass
    try:
        err = e.read()
        if err:
            chunks.append(err)
    except Exception:
        pass
    return b"".join(chunks).decode("utf-8", "replace")


def main() -> None:
    s = connect("39.105.20.113", pem=False)
    for unit in (
        "agentlink-supplier-a-erp",
        "agentlink-supplier-b-erp",
        "agentlink-supplier-c-erp",
    ):
        print(run(s, f"systemctl restart {unit}; sleep 2; systemctl is-active {unit}", 45), flush=True)
    s.close()

    b = connect("81.70.46.119", pem=True)
    print(run(b, "systemctl restart agentlink-buyer-a; sleep 4; systemctl is-active agentlink-buyer-a", 60), flush=True)
    sftp = b.open_sftp()
    sftp.put(str(ROOT / "scripts/_probe_group_quick.py"), "/tmp/_probe_group_quick.py")
    sftp.close()
    time.sleep(2)
    out = run(
        b,
        "set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a; "
        "cd /opt/agentlink && PYTHONPATH=/opt/agentlink .venv/bin/python /tmp/_probe_group_quick.py",
        180,
    )
    print(out[-3000:], flush=True)
    b.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
