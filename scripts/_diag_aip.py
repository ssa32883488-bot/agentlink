# -*- coding: utf-8 -*-
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
set -a; [ -f /opt/agentlink/.env ] && . /opt/agentlink/.env; set +a
echo SUPPLIER_A_RPC_URL=$SUPPLIER_A_RPC_URL
echo AIP_SSL_INSECURE=$AIP_SSL_INSECURE
curl -sk -o /dev/null -w "curl_domain=%{http_code}\n" --connect-timeout 8 https://moknobita.xyz:8011/health || echo curl_domain_fail
curl -sk -o /dev/null -w "curl_ip=%{http_code}\n" --connect-timeout 8 https://39.105.20.113:8011/health || echo curl_ip_fail
cd /opt/agentlink && .venv/bin/python - <<'PY'
import asyncio, os, traceback
from commerce_v2.protocol_bridge import aip_call, extract_business
async def main():
    url = os.getenv("SUPPLIER_A_RPC_URL", "https://moknobita.xyz:8011/rpc")
    try:
        raw = await aip_call(
            url,
            os.getenv("SUPPLIER_A_AIC", "supplier-a-local-aic"),
            {"schema_type": "v2.initial_quote", "sku": "RM-CASTER-300", "quantity": 300, "business_id": "smoke2"},
            leader_aic=os.getenv("BUYER_A_AIC", "buyer-a-local-aic"),
            local_agent_id="buyer-a",
        )
        biz = extract_business(raw)
        print("AIP_OK", raw.get("state"), biz.get("schema_type") if isinstance(biz, dict) else None, bool(biz.get("quote") if isinstance(biz, dict) else False))
    except Exception:
        traceback.print_exc()
asyncio.run(main())
PY
"""
    _i, o, _e = c.exec_command(cmd, timeout=90, get_pty=True)
    print(o.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
