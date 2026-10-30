# -*- coding: utf-8 -*-
"""Deploy: decide_order respects quantity=500 + Java physical specs on initial quote."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "java-suppliers"
GRADLE = JS / ".tools" / "gradle-8.10.2" / "bin" / "gradle.bat"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

JAR_MAP = {
    "supplier-a/build/libs/supplier-a-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-a.jar",
    "supplier-b/build/libs/supplier-b-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-b.jar",
    "supplier-c/build/libs/supplier-c-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-c.jar",
}
BUYER = [
    "commerce/flow_service.py",
    "commerce/chat_buyer_wit.py",
    "commerce/choice_actions.py",
    "commerce/buyer_tools/service.py",
]


def main() -> None:
    print("BUILD jars", flush=True)
    subprocess.check_call(
        [str(GRADLE), ":supplier-a:bootJar", ":supplier-b:bootJar", ":supplier-c:bootJar", "-q"],
        cwd=str(JS),
    )
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    with SCPClient(c.get_transport()) as scp:
        for local, remote in JAR_MAP.items():
            scp.put(str(JS / local), remote)
            print("put", local, flush=True)
    _, o, e = c.exec_command(
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "sleep 40; systemctl is-active agentlink-supplier-a",
        timeout=120,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()

    c2 = paramiko.SSHClient()
    c2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c2.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c2.open_sftp()
    for rel in BUYER:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put buyer", rel, flush=True)
    sftp.close()
    _, o, e = c2.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 4; systemctl is-active agentlink-buyer-a",
        timeout=60,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c2.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
