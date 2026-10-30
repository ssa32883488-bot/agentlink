"""Probe Wutong discovery API shapes until one returns ADP result."""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BASE = "https://wt.ioa.pub/discovery"

PAYLOADS = [
    {"type": "explicit", "query": "座椅原料供应商 报价", "limit": 5},
    {"query": "座椅原料供应商 报价", "limit": 5},
    {"type": "explicit", "query": "采联供应商"},
]

PATHS = [
    "",
    "/",
    "/discover",
    "/v1/discover",
    "/api/discover",
    "/adp/discover",
    "/rpc",
    "/jsonrpc",
]


def local_probe() -> None:
    print("=== local probe ===")
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        r = client.get(BASE)
        print("GET base", r.status_code, r.text[:200])
        for path in PATHS:
            url = BASE.rstrip("/") + path
            for i, payload in enumerate(PAYLOADS[:1]):
                try:
                    r = client.post(url, json=payload)
                    print(f"POST {path or '(root)'} #{i} -> {r.status_code} {r.text[:160].replace(chr(10),' ')}")
                except Exception as e:
                    print(f"POST {path or '(root)'} ERR {e}")
        # openapi / swagger
        for p in ["/openapi.json", "/docs", "/redoc", "/swagger.json", "/.well-known/adp"]:
            try:
                r = client.get(BASE.rstrip("/") + p)
                print(f"GET {p} -> {r.status_code} {r.text[:120].replace(chr(10),' ')}")
            except Exception as e:
                print(f"GET {p} ERR {e}")


REMOTE = r"""
python3 - <<'PY'
import json, urllib.request, ssl
ctx = ssl.create_default_context()
base = "https://wt.ioa.pub/discovery"
payload = json.dumps({"type":"explicit","query":"座椅原料供应商","limit":5}).encode()
paths = ["", "/", "/discover", "/v1/discover", "/api/v1/discover", "/adp/discover", "/rpc"]
for p in paths:
    url = base.rstrip("/") + p
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json","Accept":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            body = r.read()[:300]
            print("POST", repr(p), r.status, body)
    except Exception as e:
        print("POST", repr(p), type(e).__name__, e)
# also try GET with query
for p in ["/discover?query=supplier&limit=5", "/?query=supplier"]:
    url = base.rstrip("/") + p
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=15) as r:
            print("GET", p, r.status, r.read()[:200])
    except Exception as e:
        print("GET", p, type(e).__name__, e)
PY
"""


def remote_probe() -> None:
    print("=== remote probe (buyer host) ===")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    _, stdout, stderr = c.exec_command(REMOTE, timeout=90, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    local_probe()
    remote_probe()
