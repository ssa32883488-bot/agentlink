"""Probe ADP queries for supplier C (8R39K3 / scarce-quote)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r'''
cd /opt/agentlink
.venv/bin/python <<'PY'
import asyncio, json, os
from commerce.discovery import _post_discover, _platform_discover_urls, _extract_platform_acs, _acs_to_candidate, _is_supplier_candidate

async def main():
    base = (os.getenv("ACPS_DISCOVERY_URL") or "https://wt.ioa.pub/discovery").rstrip("/")
    urls = _platform_discover_urls(base)
    queries = [
        "agentlink.supplier.scarce-quote",
        "库存紧张 供应商",
        "采联供应商智能体C",
        "8R39K3",
        "工业原料供应商 报价",
        "agentlink.supplier.quote",
        "agentlink.supplier.custom-quote",
        "substitute scarce",
    ]
    url = urls[0]
    print("url", url)
    for q in queries:
        try:
            body = await _post_discover(url, q, limit=20)
        except Exception as e:
            print("Q", q, "ERR", e)
            continue
        acs_list = _extract_platform_acs(body)
        hits = []
        for acs in acs_list:
            c = _acs_to_candidate(acs, source="platform_adp")
            aic = str(c.get("aic") or "")
            name = str(c.get("name") or "")
            if "8R39K3" in aic or ("供应商" in name and "C" in name) or "scarce" in json.dumps(acs, ensure_ascii=False):
                hits.append({"name": name, "aic": aic[-20:], "agent_id": c.get("agent_id"), "skill": acs.get("_matched_skill")})
        print(f"Q={q!r} total={len(acs_list)} c_hits={len(hits)}")
        for h in hits[:5]:
            print(" ", h)
asyncio.run(main())
PY
'''


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
    _, o, _ = c.exec_command(REMOTE, timeout=180, get_pty=True)
    print(o.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
