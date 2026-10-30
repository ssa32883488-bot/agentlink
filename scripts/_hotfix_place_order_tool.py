# -*- coding: utf-8 -*-
"""热修：下单改为供应商工具 place_order，仅 place_order=on（用户明确下单）时落单。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce_v2/supplier_tools.py",
    "commerce_v2/partner_supplier.py",
    "commerce_v2/order_sync.py",
    "commerce_v2/buyer_path_normal.py",
    "commerce_v2/buyer_path_group.py",
    "commerce_v2/routes.py",
    "commerce_v2/partner_routes.py",
]
SUP_FILES = [
    "commerce_v2/supplier_tools.py",
    "commerce_v2/partner_supplier.py",
    "commerce_v2/order_sync.py",
    "commerce_v2/partner_routes.py",
]


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> None:
    print("$", cmd[:160], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    print(o.read().decode("utf-8", errors="replace")[-1800:], flush=True)


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in files:
            remote = f"/opt/agentlink/{rel}"
            parent = str(Path(remote).parent).replace("\\", "/")
            run(c, f"mkdir -p {parent}")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")


def main() -> None:
    cb = connect("buyer")
    put(cb, BUYER_FILES)
    run(
        cb,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "sleep 2; systemctl is-active agentlink-buyer-a",
    )
    cb.close()

    cs = connect("supplier")
    put(cs, SUP_FILES)
    run(
        cs,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "sleep 2; systemctl is-active agentlink-supplier-b; "
        "curl -sk https://127.0.0.1:8011/api/v2/tools | python3 -m json.tool | head -40",
    )
    # 验证：无 on 拒绝；有 on 接收
    run(
        cs,
        r"""python3 - <<'PY'
from commerce_v2 import partner_supplier as p
r=p.handle_envelope('supplier-b', {'schema_type':'v2.place_order','order':{'order_id':'ord-test-off','buyer_id':'buyer-a','supplier_id':'supplier-b','sku':'X','qty':1}})
print('off', r.get('ok'), r.get('schema_type'), r.get('error','')[:60])
r2=p.handle_envelope('supplier-b', {'schema_type':'v2.place_order','place_order':'on','order':{'order_id':'ord-test-on-demo','buyer_id':'buyer-a','supplier_id':'supplier-b','sku':'RM-FABRIC-PRO','name':'demo','qty':1,'unit_price':1,'goods_total':1,'buyer_ack':False,'supplier_ack':False,'effective':False,'place_order':'on'}})
print('on', r2.get('ok'), r2.get('schema_type'), r2.get('message','')[:80])
PY""",
    )
    cs.close()
    print("HOTFIX_PLACE_ORDER_TOOL_DONE", flush=True)


if __name__ == "__main__":
    main()
