# -*- coding: utf-8 -*-
"""把采购侧供应 RPC 从域名改为 IP（腾讯云解析 moknobita 失败）。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    cmd = r"""
APP=/opt/agentlink
upsert() { key="$1"; val="$2"; if grep -q "^${key}=" "$APP/.env" 2>/dev/null; then sed -i "s|^${key}=.*|${key}=${val}|" "$APP/.env"; else echo "${key}=${val}" >> "$APP/.env"; fi; }
upsert SUPPLIER_A_RPC_URL "https://39.105.20.113:8011/rpc"
upsert SUPPLIER_B_RPC_URL "https://39.105.20.113:8013/rpc"
upsert SUPPLIER_C_RPC_URL "https://39.105.20.113:8014/rpc"
upsert AIP_SSL_INSECURE "1"
upsert V2_LOCAL_PARTNERS "0"
grep -E 'SUPPLIER_|AIP_SSL|V2_LOCAL' "$APP/.env"
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
sleep 2
systemctl is-active agentlink-buyer-a
set -a; . "$APP/.env"; set +a
cd /opt/agentlink && .venv/bin/python - <<'PY'
import asyncio, os
from commerce_v2.protocol_bridge import aip_call, extract_business
async def main():
    print("envA", os.getenv("SUPPLIER_A_RPC_URL"))
    for name, url, aic in [
        ("A", os.getenv("SUPPLIER_A_RPC_URL", "https://39.105.20.113:8011/rpc"), os.getenv("SUPPLIER_A_AIC", "supplier-a-local-aic")),
        ("C", os.getenv("SUPPLIER_C_RPC_URL", "https://39.105.20.113:8014/rpc"), os.getenv("SUPPLIER_C_AIC", "supplier-c-local-aic")),
    ]:
        try:
            raw = await aip_call(
                url,
                aic,
                {"schema_type": "v2.initial_quote", "sku": "RM-CASTER-300", "quantity": 300, "business_id": f"fix-{name}"},
                leader_aic=os.getenv("BUYER_A_AIC", "buyer-a-local-aic"),
                local_agent_id="buyer-a",
            )
            biz = extract_business(raw) or {}
            q = biz.get("quote") or {}
            print(f"AIP_{name}_OK state={raw.get('state')} unit={q.get('unit_price')} schema={biz.get('schema_type')} keys={list(biz.keys())[:8]}")
        except Exception as e:
            print(f"AIP_{name}_ERR", type(e).__name__, e)
asyncio.run(main())
PY
"""
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    print(o.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
