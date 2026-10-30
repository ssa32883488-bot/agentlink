# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def dump(host: str, auth: str) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(
        hostname=host,
        username="root",
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    if auth == "pem":
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    cmd = r"""
systemctl list-units --type=service --all --no-pager | sed -n '/agentlink\|ui/Ip'
echo '--- unit files ---'
ls /etc/systemd/system/agentlink* 2>/dev/null || true
ls /etc/systemd/system/*ui* 2>/dev/null || true
echo '--- listen ---'
ss -lntp | sed -n '/8090\|8091\|8092\|8095\|8093\|8094/p' || netstat -lntp 2>/dev/null | sed -n '/809/p'
"""
    _, o, e = c.exec_command(cmd, timeout=40, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    c.close()


if __name__ == "__main__":
    print("==== tencent ====", flush=True)
    dump("81.70.46.119", "pem")
    print("==== aliyun ====", flush=True)
    dump("39.105.20.113", "pw")
