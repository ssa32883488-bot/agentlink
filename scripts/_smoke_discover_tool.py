"""Call discover.suppliers tool path without full LLM chat."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
CHECK = r"""
cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'
import asyncio, json
from commerce.buyer_tools.service import get_buyer_tools

async def main():
    tools = get_buyer_tools()
    out = await tools.discover_suppliers_tool({
        "product_name": "重型脚轮",
        "quantity": 500,
        "query": "脚轮 供应商",
        "limit": 5,
    })
    slim = {
        "ok": out.get("ok"),
        "case_id": out.get("case_id"),
        "source": out.get("source"),
        "n": len(out.get("candidates") or []),
        "ui_form": (out.get("ui_hint") or {}).get("form"),
        "platform_error": out.get("platform_error"),
        "cand0": (out.get("candidates") or [{}])[0].get("candidate_id") if out.get("candidates") else None,
    }
    print(json.dumps(slim, ensure_ascii=False))
    mem = tools.memory.extract(out["case_id"], keys=["last_discover_candidates"])
    print("mem_keys", list((mem.get("entries") or {}).keys()))

asyncio.run(main())
PY
"""


def main() -> None:
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
    _, stdout, stderr = c.exec_command(CHECK, timeout=120, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR:", err)
    c.close()


if __name__ == "__main__":
    main()
