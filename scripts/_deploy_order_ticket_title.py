# -*- coding: utf-8 -*-
"""Deploy order ticket title/id fix (combo brief must not leak into supplier sales title)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
REL = "commerce/order_tickets.py"

CHECK = r"""
cd /opt/agentlink
.venv/bin/python - <<'PY'
from commerce.order_tickets import _order_summary, _ticket_id_for_case, spawn_order_ticket_from_case

case = {
  'case_id': 'case-titlefix01',
  'selected_supplier': 'supplier-a',
  'brief': {
    'product_name': '重型脚轮300kg × 500 + 高档座椅面料 × 500',
    'quantity': 1000,
    'lines': [
      {'sku': 'RM-CASTER-300', 'name': '重型脚轮300kg', 'qty': 500},
      {'sku': 'RM-FABRIC-PRO', 'name': '高档座椅面料', 'qty': 500},
    ],
  },
  'order_draft': {
    'payload': {
      'product_name': '重型脚轮300kg',
      'sku': 'RM-CASTER-300',
      'quantity': 500,
      'unit_price': 18.0,
      'goods_total': 9000.0,
      'supplier_agent_id': 'supplier-a',
      'currency': 'CNY',
    }
  },
}
s = _order_summary(case)
assert s['product_name'] == '重型脚轮300kg', s
assert s['quantity'] == 500, s
assert '面料' not in (s['product_name'] or '')
tid = _ticket_id_for_case('case-titlefix01', supplier='supplier-a', sku='RM-CASTER-300')
assert 'supplier' in tid or 'a' in tid, tid
assert 'CASTER' in tid or 'RM' in tid, tid
print('TITLE_SUMMARY_OK', s['product_name'], s['quantity'], tid)
PY
"""


def put_and_check(c: paramiko.SSHClient, restart: str) -> None:
    sftp = c.open_sftp()
    sftp.put(str(ROOT / REL), f"/opt/agentlink/{REL}")
    sftp.close()
    print("put", REL, flush=True)
    _, o, e = c.exec_command(f"{restart}; {CHECK}", timeout=90, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    sys.stdout.write(out + "\n")
    if "TITLE_SUMMARY_OK" not in out:
        raise SystemExit("check failed")


def main() -> None:
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put_and_check(
        b,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 2; "
        "systemctl is-active agentlink-buyer-a",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    # suppliers need mirror accept path; same module
    put_and_check(
        s,
        "systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp 2>/dev/null; "
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 3; "
        "systemctl is-active agentlink-supplier-a",
    )
    s.close()
    print("DEPLOY_ORDER_TICKET_TITLE_DONE", flush=True)


if __name__ == "__main__":
    main()
