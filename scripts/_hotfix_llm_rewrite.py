# -*- coding: utf-8 -*-
"""热修：删除硬规则改写，改走 LLM；同步 LLM 环境并验收坐垫。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
LOCAL_ENV = ROOT / ".env"

FILES = [
    "commerce_v2/llm_rewrite.py",
    "commerce_v2/buyer_path_normal.py",
    "commerce_v2/buyer_path_group.py",
    "commerce_v2/catalog.py",
    "commerce_v2/protocol_bridge.py",
]

LLM_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


def _local_llm_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not LOCAL_ENV.is_file():
        return out
    for raw in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k in LLM_KEYS:
            out[k] = v
    return out


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
    print(text[-3500:], flush=True)
    return text


def upsert_env(c: paramiko.SSHClient, key: str, val: str) -> None:
    # avoid shell injection via python literals
    run(
        c,
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"key, val = {key!r}, {val!r}\n"
        "p = Path('/opt/agentlink/.env')\n"
        "lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else []\n"
        "out, found = [], False\n"
        "for ln in lines:\n"
        "    if ln.startswith(key + '='):\n"
        "        out.append(f'{key}={val}'); found = True\n"
        "    else:\n"
        "        out.append(ln)\n"
        "if not found:\n"
        "    out.append(f'{key}={val}')\n"
        "p.write_text('\\n'.join(out) + '\\n', encoding='utf-8')\n"
        "print('upsert', key)\n"
        "PY",
    )


def main() -> None:
    llm = _local_llm_env()
    assert llm.get("LLM_API_KEY"), "local .env missing LLM_API_KEY"
    c = connect()
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            run(c, f"mkdir -p $(dirname {remote})")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")
    for k in LLM_KEYS:
        if k in llm:
            upsert_env(c, k, llm[k])
    # 确保 wit/llm 不被 rules 关掉；改写只依赖 LLM_API_KEY
    upsert_env(c, "BUYER_CHAT_ENGINE", "wit")
    run(
        c,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 4; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b",
    )
    # write verify script
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
print("LLM_MODEL", os.getenv("LLM_MODEL"), "KEY", bool(os.getenv("LLM_API_KEY")))
from commerce_v2.llm_rewrite import rewrite_demand_llm

async def unit():
    b = await rewrite_demand_llm("帮我采购400坐垫", "buyer-a")
    print("UNIT", b.get("rewrite_engine"), b.get("sku"), b.get("rewritten_query"))
    assert "脚轮" not in (b.get("rewritten_query") or "")
    assert "坐垫" in (b.get("rewritten_query") or b.get("name") or "")
    print("UNIT_OK")
asyncio.run(unit())

CTX = ssl._create_unverified_context()
body = json.dumps({"title": "坐垫LLM改写"}).encode()
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
meta = case.get("discovery_meta") or {}
print("CHAT_ENGINE", brief.get("rewrite_engine"))
print("CHAT_BRIEF", brief.get("rewritten_query"), brief.get("sku"))
print("CHAT_SOURCE", meta.get("source"))
print("REPLY", (out.get("reply") or "")[:220].replace("\n", " / "))
assert "脚轮" not in (brief.get("rewritten_query") or "")
assert "坐垫" in (brief.get("rewritten_query") or brief.get("name") or out.get("reply") or "")
print("CHAT_OK")
'''
    sftp = c.open_sftp()
    with sftp.file("/tmp/_verify_llm_rewrite.py", "w") as f:
        f.write(verify)
    sftp.close()
    run(c, "/opt/agentlink/.venv/bin/python /tmp/_verify_llm_rewrite.py")
    c.close()
    print("HOTFIX_LLM_REWRITE_DONE", flush=True)


if __name__ == "__main__":
    main()
