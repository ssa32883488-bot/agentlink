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
    print("==== aliyun supplier-a ====")
    print(
        run(
            "39.105.20.113",
            "tail -n 80 /var/log/agentlink/supplier-a.log 2>/dev/null; "
            "echo '---'; "
            "curl -sk -X POST https://127.0.0.1:8011/group/join "
            "-H 'Content-Type: application/json' -d '{}' | head -c 400; echo",
            pem=False,
        )[-5000:]
    )
    print("==== tencent logistics ====")
    print(
        run(
            "81.70.46.119",
            "tail -n 40 /var/log/agentlink/logistics.log 2>/dev/null; "
            "echo '---'; "
            "curl -sk -X POST https://127.0.0.1:8015/group/join "
            "-H 'Content-Type: application/json' -d '{}' | head -c 400; echo",
            pem=True,
        )[-3000:]
    )


if __name__ == "__main__":
    main()
