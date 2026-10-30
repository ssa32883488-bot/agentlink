# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def run(host: str, cmd: str, *, pem: bool) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
    text = (o.read() + e.read()).decode("utf-8", "replace")
    c.close()
    return text


def main() -> None:
    print(
        run(
            "39.105.20.113",
            "systemctl list-units 'agentlink-*' --no-pager | head -40; echo ===; "
            "ss -lntp | grep -E '8011|8013|8014|8111|8113|8114|9011' || netstat -lntp | grep -E '8011|8013|8014|811'; echo ===; "
            "grep -E 'PORT|RPC|GROUP|JOIN' /etc/agentlink/supplier-a.env 2>/dev/null | head -30; echo ===; "
            "for p in 8011 8111 9011 18011; do "
            "echo PORT$p; curl -sk --max-time 4 https://127.0.0.1:$p/health; echo; "
            "curl -sk --max-time 4 -X POST https://127.0.0.1:$p/group/join -H 'Content-Type: application/json' "
            "-d '{\"params\":{\"group\":{\"groupId\":\"g\"}}}' | head -c 200; echo; done",
            pem=False,
        )[-7000:]
    )


if __name__ == "__main__":
    main()
