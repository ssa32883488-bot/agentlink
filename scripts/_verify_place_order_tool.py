# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _i, o, e = c.exec_command(cmd, timeout=60)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def main() -> None:
    cs = connect("supplier")
    print("=== tools endpoint ===")
    print(run(cs, "curl -sk https://127.0.0.1:8011/api/v2/tools; echo; curl -sk http://127.0.0.1:8011/api/v2/tools; echo; ss -lntp | grep 8011 | head -3"))
    print("=== gate test ===")
    print(
        run(
            cs,
            "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
            "from commerce_v2 import partner_supplier as p\n"
            "r=p.handle_envelope('supplier-b', {'schema_type':'v2.place_order','order':{'order_id':'ord-test-off2','buyer_id':'buyer-a','supplier_id':'supplier-b','sku':'X','qty':1}})\n"
            "print('off', r.get('ok'), r.get('schema_type'), (r.get('error') or '')[:80])\n"
            "r2=p.handle_envelope('supplier-b', {'schema_type':'v2.place_order','place_order':'on','order':{'order_id':'ord-test-on-demo2','buyer_id':'buyer-a','supplier_id':'supplier-b','sku':'RM-FABRIC-PRO','name':'demo','qty':1,'unit_price':1,'goods_total':1,'buyer_ack':False,'supplier_ack':False,'effective':False,'place_order':'on'}})\n"
            "print('on', r2.get('ok'), r2.get('schema_type'), (r2.get('message') or '')[:100])\n"
            "print('tools', [t['name'] for t in p.list_tools()])\n"
            "PY",
        )
    )
    cs.close()


if __name__ == "__main__":
    main()
