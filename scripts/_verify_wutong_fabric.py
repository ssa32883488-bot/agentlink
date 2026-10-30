# -*- coding: utf-8 -*-
"""远端验收：面料改写 + 真实梧桐 ADP。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=key,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    script = r'''
import asyncio, json, os, ssl, urllib.request, sys
sys.path.insert(0, "/opt/agentlink")
os.chdir("/opt/agentlink")
for ln in open("/opt/agentlink/.env", encoding="utf-8"):
    ln = ln.strip()
    if not ln or ln.startswith("#") or "=" not in ln:
        continue
    k, v = ln.split("=", 1)
    os.environ[k] = v
print("ACPS", os.getenv("ACPS_DISCOVERY_URL"))
import httpx
print("httpx", httpx.__version__)
from commerce_v2.buyer_path_normal import rewrite_demand
from commerce_v2.protocol_bridge import discover_suppliers
brief = rewrite_demand("帮我采购300面料", "buyer-a")
print("REWRITE", brief["sku"], brief["rewritten_query"])
assert brief["sku"].startswith("RM-FABRIC"), brief

async def go():
    disc = await discover_suppliers(brief["rewritten_query"], sku=brief["sku"], agent_id="buyer-a")
    print("DISC", disc.get("source"), "degrade", disc.get("degrade"), "n", len(disc.get("candidates") or []))
    print("ERR", disc.get("error"))
    print("META", disc.get("meta"))
    for x in (disc.get("candidates") or [])[:5]:
        print(" -", x.get("agent_id"), x.get("title"))
    assert disc.get("source") == "platform_adp", disc
    assert any(str(x.get("agent_id")) == "supplier-b" for x in disc.get("candidates") or []), disc
    print("ADP_OK")
asyncio.run(go())

CTX = ssl._create_unverified_context()
body = json.dumps({"title": "面料梧桐验收"}).encode()
req = urllib.request.Request(
    "https://127.0.0.1:8010/api/erp/chat/threads",
    data=body,
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
    th = json.loads(r.read().decode())
chat = json.dumps({"text": "帮我采购300面料", "thread_id": th["id"]}).encode()
req = urllib.request.Request(
    "https://127.0.0.1:8010/api/erp/chat",
    data=chat,
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, context=CTX, timeout=180) as r:
    out = json.loads(r.read().decode())
case = out.get("case") or {}
meta = case.get("discovery_meta") or {}
brief = case.get("brief") or {}
print("CHAT_SOURCE", meta.get("source"), "degrade", meta.get("degrade"))
print("CHAT_BRIEF", brief.get("rewritten_query"), brief.get("sku"))
cands = case.get("candidates") or []
print("CANDS", [(x.get("agent_id"), x.get("title")) for x in cands])
print("REPLY", (out.get("reply") or "")[:220].replace("\n", " / "))
assert "脚轮" not in (brief.get("rewritten_query") or "")
assert brief.get("sku", "").startswith("RM-FABRIC")
assert meta.get("source") == "platform_adp", meta
assert any(str(x.get("agent_id")) == "supplier-b" for x in cands), cands
print("CHAT_OK")
'''
    sftp = c.open_sftp()
    with sftp.file("/tmp/_verify_wutong_fabric.py", "w") as f:
        f.write(script)
    sftp.close()
    print("$ /opt/agentlink/.venv/bin/python /tmp/_verify_wutong_fabric.py", flush=True)
    _i, o, _e = c.exec_command(
        "/opt/agentlink/.venv/bin/python /tmp/_verify_wutong_fabric.py",
        timeout=240,
        get_pty=True,
    )
    print(o.read().decode("utf-8", errors="replace"), flush=True)
    c.close()


if __name__ == "__main__":
    main()
