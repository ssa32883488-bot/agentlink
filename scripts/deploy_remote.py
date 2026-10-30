"""上传并安装到腾讯云(buyer) / 阿里云(supplier)。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
TAR = ROOT / "dist" / "agentlink_remote.tar.gz"
INSTALL_SH = ROOT / "scripts" / "remote_install.sh"
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

BUYER = {"host": "81.70.46.119", "user": "root", "auth": "key", "role": "buyer"}
SUPPLIER = {
    "host": "39.105.20.113",
    "user": "root",
    "auth": "password",
    "password": os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"),
    "role": "supplier",
}


def connect(spec: dict) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if spec["auth"] == "key":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(spec["host"], username=spec["user"], pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            spec["host"],
            username=spec["user"],
            password=spec["password"],
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 600) -> None:
    print(f"$ {cmd}")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if out:
        print(out[-4000:])
    if err:
        print(err[-2000:], file=sys.stderr)
    if code != 0:
        raise SystemExit(f"remote exit {code}: {cmd}")


def deploy(spec: dict) -> None:
    assert TAR.is_file(), f"missing {TAR}"
    assert INSTALL_SH.is_file()
    print(f"\n==== deploy {spec['role']} {spec['host']} ====")
    c = connect(spec)
    run(c, "mkdir -p /opt/agentlink_bundle /tmp")
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(TAR), "/tmp/agentlink_remote.tar.gz")
        scp.put(str(INSTALL_SH), "/tmp/remote_install.sh")
    run(c, "sed -i 's/\r$//' /tmp/remote_install.sh || true")
    run(c, "rm -rf /opt/agentlink_bundle && mkdir -p /opt/agentlink_bundle && tar -xzf /tmp/agentlink_remote.tar.gz -C /opt/agentlink_bundle")
    run(c, "chmod +x /tmp/remote_install.sh && bash /tmp/remote_install.sh " + spec["role"] + " /opt/agentlink_bundle", timeout=900)
    c.close()
    print(f"done {spec['host']}")


def main() -> None:
    targets = sys.argv[1:] or ["buyer", "supplier"]
    if "buyer" in targets:
        deploy(BUYER)
    if "supplier" in targets:
        deploy(SUPPLIER)


if __name__ == "__main__":
    main()
