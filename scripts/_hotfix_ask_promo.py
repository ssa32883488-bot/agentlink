# -*- coding: utf-8 -*-
"""热修：去掉「探量」；议价改为直接询问供应优惠政策。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
FILES = [
    "commerce_v2/partner_supplier.py",
    "commerce_v2/buyer_path_normal.py",
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
    print("$", cmd[:140], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    print(o.read().decode("utf-8", errors="replace")[-1200:], flush=True)


def patch(role: str, units: str) -> None:
    print(f"==== {role} ====", flush=True)
    c = connect(role)
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            run(c, f"mkdir -p $(dirname {remote})")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")
    run(c, f"systemctl restart {units}; sleep 2; systemctl is-active {units}")
    c.close()


def main() -> None:
    patch("buyer", "agentlink-buyer-a agentlink-buyer-b")
    patch("supplier", "agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c")
    # quick unit on buyer
    c = connect("buyer")
    run(
        c,
        r"""/opt/agentlink/.venv/bin/python - <<'PY'
import asyncio, sys, os
sys.path.insert(0,'/opt/agentlink'); os.chdir('/opt/agentlink')
from commerce_v2 import partner_supplier as psup
r = psup.handle_envelope('supplier-b', {'schema_type':'v2.promo_query','sku':'RM-FOAM-MEM','question':'有什么优惠政策'})
print('PROMO', r.get('message'))
assert '优惠' in (r.get('message') or '') or '挂牌' in (r.get('message') or '')
q = psup.handle_envelope('supplier-b', {'schema_type':'v2.bargain','sku':'RM-FOAM-MEM','quantity':400})
print('QTY400', (q.get('quote') or {}).get('qty'), (q.get('quote') or {}).get('promo_reason'))
assert (q.get('quote') or {}).get('qty') == 400
print('OK')
PY""",
    )
    c.close()
    print("HOTFIX_ASK_PROMO_DONE", flush=True)


if __name__ == "__main__":
    main()
