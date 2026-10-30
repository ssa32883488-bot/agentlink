# -*- coding: utf-8 -*-
"""热修：改写前检索画像/库存/目录，再 LLM 消歧；验收坐垫→RM-FOAM-MEM。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

FILES = [
    "commerce_v2/catalog.py",
    "commerce_v2/rewrite_grounding.py",
    "commerce_v2/llm_rewrite.py",
    "commerce_v2/buyer_path_normal.py",
    "commerce_v2/partner_routes.py",
]


def connect() -> paramiko.SSHClient:
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
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd[:140], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=300, get_pty=True)
    text = o.read().decode("utf-8", errors="replace")
    print(text[-4000:], flush=True)
    return text


def main() -> None:
    c = connect()
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            run(c, f"mkdir -p $(dirname {remote})")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")
    run(
        c,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b "
        "agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c 2>/dev/null || "
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; "
        "sleep 4; systemctl is-active agentlink-buyer-a",
    )
    verify = r'''
import asyncio, json, os, ssl, urllib.request, sys
sys.path.insert(0, "/opt/agentlink")
os.chdir("/opt/agentlink")
for ln in open("/opt/agentlink/.env", encoding="utf-8"):
    ln = ln.strip()
    if not ln or ln.startswith("#") or "=" not in ln:
        continue
    k, v = ln.split("=", 1)
    os.environ[k] = v

from commerce_v2.rewrite_grounding import gather_rewrite_evidence
from commerce_v2.llm_rewrite import rewrite_demand_llm

ev = gather_rewrite_evidence("buyer-a")
print("INV", [(x.get("code"), x.get("name")) for x in (ev.get("buyer_inventory") or [])])
assert any(x.get("code") == "RM-FOAM-MEM" for x in (ev.get("buyer_inventory") or [])), ev.get("buyer_inventory")
assert any(x.get("sku") == "RM-FOAM-MEM" for x in (ev.get("supplier_catalog") or [])), "catalog missing foam"

async def unit():
    b = await rewrite_demand_llm("帮我采购400坐垫", "buyer-a")
    print("UNIT", b.get("rewrite_engine"), b.get("sku"), b.get("rewritten_query"))
    print("HINT", b.get("hint"))
    print("USED", b.get("evidence_used"))
    assert "脚轮" not in (b.get("rewritten_query") or "")
    assert b.get("sku") == "RM-FOAM-MEM" or "坐垫" in (b.get("rewritten_query") or "")
    assert "坐垫" in (b.get("rewritten_query") or b.get("name") or "")
    print("UNIT_OK")
asyncio.run(unit())

CTX = ssl._create_unverified_context()
body = json.dumps({"title": "坐垫有据改写"}).encode()
req = urllib.request.Request(
    "https://127.0.0.1:8010/api/erp/chat/threads",
    data=body, method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
    th = json.loads(r.read().decode())
chat = json.dumps({"text": "帮我采购400坐垫", "thread_id": th["id"]}).encode()
req = urllib.request.Request(
    "https://127.0.0.1:8010/api/erp/chat",
    data=chat, method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, context=CTX, timeout=180) as r:
    out = json.loads(r.read().decode())
case = out.get("case") or {}
brief = case.get("brief") or {}
print("CHAT_ENGINE", brief.get("rewrite_engine"))
print("CHAT_SKU", brief.get("sku"), brief.get("rewritten_query"))
print("CHAT_HINT", brief.get("hint"))
print("CHAT_USED", brief.get("evidence_used"))
assert "脚轮" not in (brief.get("rewritten_query") or "")
assert "坐垫" in (brief.get("rewritten_query") or brief.get("name") or "")
assert brief.get("sku") == "RM-FOAM-MEM"
print("CHAT_OK")
'''
    sftp = c.open_sftp()
    with sftp.file("/tmp/_verify_grounded_rewrite.py", "w") as f:
        f.write(verify)
    sftp.close()
    run(c, "/opt/agentlink/.venv/bin/python /tmp/_verify_grounded_rewrite.py")
    c.close()
    print("HOTFIX_GROUNDED_REWRITE_DONE", flush=True)


if __name__ == "__main__":
    main()
