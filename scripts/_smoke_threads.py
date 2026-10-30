# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
CMD = r"""
/opt/agentlink/.venv/bin/python <<'PY'
import json, urllib.request, ssl
ctx = ssl._create_unverified_context()

def call(path, data=None):
    req = urllib.request.Request("https://127.0.0.1:8010" + path, method="GET" if data is None else "POST")
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        return json.loads(r.read().decode())

t1 = call("/api/erp/chat/threads", {"title": "窗一"})
t2 = call("/api/erp/chat/threads", {"title": "窗二"})
print("t1", t1.get("id"), "t2", t2.get("id"))
call(f"/api/erp/chat/threads/{t1['id']}/activate", {})
items = call("/api/erp/chat/threads")["items"]
print("threads", [(x["id"], x["title"]) for x in items])
print("conv_t1_n", len(call(f"/api/erp/conversations?thread_id={t1['id']}")["items"]))
print("conv_t2_n", len(call(f"/api/erp/conversations?thread_id={t2['id']}")["items"]))
print("shared", call("/api/erp/shared-facts"))
print("OK")
PY
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(CMD, timeout=60, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    c.close()


if __name__ == "__main__":
    main()
