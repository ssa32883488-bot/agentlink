# -*- coding: utf-8 -*-
"""双云 v2 冒烟：chat-engine / health / 一句采购。"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
CTX = ssl._create_unverified_context()


def http_json(url: str, data: dict | None = None) -> dict:
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method="POST" if body else "GET",
    )
    with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ssh_run(host: str, auth: str, cmd: str) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if auth == "key":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(host, username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect(host, username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    _i, o, _e = c.exec_command(cmd, timeout=90, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    c.close()
    return out


def main() -> None:
    print("== buyer local via ssh ==")
    print(
        ssh_run(
            "81.70.46.119",
            "key",
            "ss -lntp | grep -E '8010|8012|8015' || true; "
            "for p in 8010 8012 8015; do echo ==$p==; "
            "curl -sk https://127.0.0.1:$p/api/erp/chat-engine; echo; "
            "curl -sk https://127.0.0.1:$p/api/v2/health; echo; done; "
            "grep AGENTLINK_RUNTIME /opt/agentlink/.env || true",
        )
    )
    print("== supplier local via ssh ==")
    print(
        ssh_run(
            "39.105.20.113",
            "password",
            "ss -lntp | grep -E '8011|8013|8014' || true; "
            "for p in 8011 8013 8014; do echo ==$p==; "
            "curl -sk https://127.0.0.1:$p/api/erp/chat-engine; echo; "
            "curl -sk https://127.0.0.1:$p/api/v2/health; echo; done; "
            "grep AGENTLINK_RUNTIME /opt/agentlink/.env || true",
        )
    )
    # 公网探测（若 DNS/安全组可达）
    for label, url in [
        ("buyer-a public", "https://ashui.online:8010/api/erp/chat-engine"),
        ("supplier-a public", "https://moknobita.xyz:8011/api/erp/chat-engine"),
    ]:
        try:
            j = http_json(url)
            print(label, j)
        except Exception as e:  # noqa: BLE001
            print(label, "FAIL", type(e).__name__, e)


if __name__ == "__main__":
    main()
