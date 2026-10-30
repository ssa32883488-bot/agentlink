# -*- coding: utf-8 -*-
"""热修：跨云工单同步 + 补推现有订单到供应侧。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce_v2/order_sync.py",
    "commerce_v2/order_ids.py",
    "commerce_v2/catalog.py",
    "commerce_v2/gates.py",
    "commerce_v2/partner_supplier.py",
    "commerce_v2/partner_logistics.py",
    "commerce_v2/buyer_path_normal.py",
    "commerce_v2/buyer_path_group.py",
    "commerce_v2/routes.py",
    "commerce_v2/partner_routes.py",
]


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(
            "81.70.46.119",
            username="root",
            pkey=key,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    else:
        c.connect(
            "39.105.20.113",
            username="root",
            password=PW,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd, flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=180, get_pty=True)
    text = o.read().decode("utf-8", errors="replace")
    print(text[-2200:], flush=True)
    return text


def put_files(c: paramiko.SSHClient) -> None:
    app = "/opt/agentlink"
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"{app}/{rel}"
            run(c, f"mkdir -p $(dirname {remote})")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")


def upsert_env(c: paramiko.SSHClient, key: str, val: str) -> None:
    run(
        c,
        f"python3 - <<'PY'\n"
        f"from pathlib import Path\n"
        f"p=Path('/opt/agentlink/.env')\n"
        f"lines=p.read_text(encoding='utf-8').splitlines() if p.exists() else []\n"
        f"out=[]; found=False\n"
        f"for ln in lines:\n"
        f"    if ln.startswith('{key}='):\n"
        f"        out.append('{key}={val}'); found=True\n"
        f"    else: out.append(ln)\n"
        f"if not found: out.append('{key}={val}')\n"
        f"p.write_text('\\n'.join(out)+'\\n', encoding='utf-8')\n"
        f"print('upsert', '{key}')\n"
        f"PY",
    )


def main() -> None:
    print("==== buyer deploy ====", flush=True)
    cb = connect("buyer")
    put_files(cb)
    run(
        cb,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics",
    )
    # dump open orders for repush
    run(
        cb,
        r"""python3 - <<'PY'
import json, ssl, urllib.request
CTX=ssl._create_unverified_context()
url='https://127.0.0.1:8010/api/erp/tickets'
with urllib.request.urlopen(url, context=CTX, timeout=20) as r:
    data=json.loads(r.read().decode())
items=data.get('items') or []
print('BUYER_TICKETS', len(items))
Path='/opt/agentlink/data/v2_orders/orders.json'
import pathlib
p=pathlib.Path(Path)
print('ORDERS_FILE', p.exists(), p)
if p.exists():
    raw=json.loads(p.read_text(encoding='utf-8'))
    print('ORDER_IDS', list((raw.get('orders') or {}).keys())[:10])
    pathlib.Path('/tmp/v2_orders_export.json').write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    print('EXPORTED')
PY""",
    )
    # fetch export via sftp
    sftp = cb.open_sftp()
    local_export = ROOT / "dist" / "_v2_orders_export.json"
    local_export.parent.mkdir(parents=True, exist_ok=True)
    try:
        sftp.get("/tmp/v2_orders_export.json", str(local_export))
        print("got export", local_export, flush=True)
    except Exception as e:
        print("no export yet", e, flush=True)
        local_export.write_text(json.dumps({"orders": {}, "logistics": {}}), encoding="utf-8")
    sftp.close()
    cb.close()

    print("==== supplier deploy ====", flush=True)
    cs = connect("supplier")
    put_files(cs)
    upsert_env(cs, "BUYER_A_RPC_URL", "https://81.70.46.119:8010/rpc")
    upsert_env(cs, "BUYER_B_RPC_URL", "https://81.70.46.119:8012/rpc")
    upsert_env(cs, "LOGISTICS_RPC_URL", "https://81.70.46.119:8015/rpc")
    upsert_env(cs, "AIP_SSL_INSECURE", "1")
    upsert_env(cs, "V2_LOCAL_PARTNERS", "0")
    run(
        cs,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c",
    )
    # upload orders and sync via API
    with SCPClient(cs.get_transport()) as scp:
        scp.put(str(local_export), "/tmp/v2_orders_export.json")
    run(
        cs,
        r"""python3 - <<'PY'
import json, ssl, urllib.request, pathlib, time
time.sleep(2)
CTX=ssl._create_unverified_context()
raw=json.loads(pathlib.Path('/tmp/v2_orders_export.json').read_text(encoding='utf-8'))
orders=raw.get('orders') or {}
print('TO_SYNC', len(orders))
ok=0
for oid, order in orders.items():
    body=json.dumps({'order': order}).encode()
    req=urllib.request.Request(
        'https://127.0.0.1:8011/api/erp/v2/orders/sync',
        data=body, method='POST',
        headers={'Content-Type':'application/json'},
    )
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=20) as r:
            print('SYNC', oid, r.status, r.read()[:120])
            ok+=1
    except Exception as e:
        print('FAIL', oid, e)
print('SYNCED', ok)
# verify tickets
with urllib.request.urlopen('https://127.0.0.1:8011/api/erp/tickets', context=CTX, timeout=20) as r:
    data=json.loads(r.read().decode())
print('SUPPLIER_A_TICKETS', len(data.get('items') or []))
for t in (data.get('items') or [])[:5]:
    print(' -', t.get('id'), t.get('title'), t.get('status'))
PY""",
    )
    cs.close()
    print("HOTFIX_ORDER_SYNC_DONE", flush=True)


if __name__ == "__main__":
    main()
