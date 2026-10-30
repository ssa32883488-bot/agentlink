# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
CTX = ssl._create_unverified_context()


def ssh(role: str, cmd: str) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    c.close()
    return out


def get(url: str):
    try:
        with urllib.request.urlopen(url, context=CTX, timeout=20) as r:
            return r.status, r.read()[:120].decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:80].decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return "ERR", f"{type(e).__name__}: {e}"


def main() -> None:
    print("== restart UI buyer ==", flush=True)
    print(
        ssh(
            "buyer",
            "systemctl restart agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; "
            "systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics "
            "agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; "
            "ss -lntp | grep -E '8010|8012|8015|8090|8092|8095' || true",
        ),
        flush=True,
    )
    print("== restart UI supplier ==", flush=True)
    print(
        ssh(
            "supplier",
            "systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; "
            "systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c "
            "agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; "
            "ss -lntp | grep -E '8011|8013|8014|8091|8093|8094' || true",
        ),
        flush=True,
    )
    checks = [
        ("buyer-a api", "https://ashui.online:8010/api/erp/chat-engine"),
        ("buyer-a conv", "https://ashui.online:8010/api/erp/conversations"),
        ("buyer-b api", "https://ashui.online:8012/api/erp/chat-engine"),
        ("logistics", "https://ashui.online:8015/api/erp/chat-engine"),
        ("ui-a", "https://ashui.online:8090/api/domain"),
        ("ui-b", "https://ashui.online:8092/api/domain"),
        ("ui-l", "https://ashui.online:8095/api/domain"),
        ("sa api", "https://moknobita.xyz:8011/api/erp/chat-engine"),
        ("sb api", "https://moknobita.xyz:8013/api/erp/chat-engine"),
        ("sc api", "https://moknobita.xyz:8014/api/erp/chat-engine"),
        ("ui-sa http", "http://moknobita.xyz:8091/api/domain"),
        ("ui-sb http", "http://moknobita.xyz:8093/api/domain"),
        ("ui-sc http", "http://moknobita.xyz:8094/api/domain"),
    ]
    print("== public checks ==", flush=True)
    for name, url in checks:
        code, body = get(url)
        print(name, code, body.replace("\n", " ")[:100], flush=True)


if __name__ == "__main__":
    main()
