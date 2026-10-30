# -*- coding: utf-8 -*-
"""一次性：上传瘦包并安装 v2 到双云。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
TAR = ROOT / "dist" / "agentlink_remote.tar.gz"
INSTALL = ROOT / "scripts" / "remote_install.sh"
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(
            "81.70.46.119",
            username="root",
            pkey=key,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    else:
        c.connect(
            "39.105.20.113",
            username="root",
            password=PW,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 900) -> None:
    print("$", cmd, flush=True)
    _stdin, stdout, _stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if out:
        print(out[-4000:], flush=True)
    if code != 0:
        raise SystemExit(f"remote exit {code}: {cmd}")


def deploy(role: str) -> None:
    assert TAR.is_file(), TAR
    print(f"==== deploy {role} tar={TAR.stat().st_size // 1024}KB ====", flush=True)
    c = connect(role)
    run(c, "mkdir -p /opt/agentlink_bundle /tmp")
    t0 = time.time()
    with SCPClient(c.get_transport()) as scp:
        print("scp tar...", flush=True)
        scp.put(str(TAR), "/tmp/agentlink_remote.tar.gz")
        print("scp install...", flush=True)
        scp.put(str(INSTALL), "/tmp/remote_install.sh")
    print(f"upload {time.time() - t0:.1f}s", flush=True)
    run(c, "sed -i 's/\\r$//' /tmp/remote_install.sh || true")
    run(
        c,
        "rm -rf /opt/agentlink_bundle && mkdir -p /opt/agentlink_bundle "
        "&& tar -xzf /tmp/agentlink_remote.tar.gz -C /opt/agentlink_bundle",
    )
    run(
        c,
        f"chmod +x /tmp/remote_install.sh && bash /tmp/remote_install.sh {role} /opt/agentlink_bundle",
        timeout=900,
    )
    # 冒烟
    if role == "buyer":
        run(
            c,
            "curl -sk https://127.0.0.1:8010/api/erp/chat-engine || curl -sk http://127.0.0.1:8010/api/erp/chat-engine || true",
        )
        run(c, "systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics || true")
    else:
        run(
            c,
            "curl -sk https://127.0.0.1:8011/api/erp/chat-engine || true; "
            "systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c || true",
        )
    c.close()
    print(f"done {role}", flush=True)


def main() -> None:
    targets = sys.argv[1:] or ["buyer", "supplier"]
    for t in targets:
        deploy(t)
    print("ALL DEPLOYED", flush=True)


if __name__ == "__main__":
    main()
