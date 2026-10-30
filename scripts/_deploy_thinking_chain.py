# -*- coding: utf-8 -*-
"""Deploy buyer thinking-chain + state_focus + split/auction choice copy."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"

FILES = [
    "commerce/chat_buyer_wit.py",
    "commerce/procurement_case.py",
    "commerce/choice_actions.py",
]

CHECK = r"""
cd /opt/agentlink
.venv/bin/python - <<'PY'
from commerce.procurement_case import describe_state_focus, STATE_FOCUS
assert 'DISCOVERING' in STATE_FOCUS
assert 'ORDER_DRAFT' in STATE_FOCUS
c = {
  'case_id': 'case-x',
  'state': 'COMPARE_PENDING',
  'brief': {
    'product_name': '脚轮+面料',
    'combo': True,
    'lines': [
      {'sku': 'RM-CASTER-300', 'name': '重型脚轮', 'qty': 500},
      {'sku': 'RM-FABRIC-PRO', 'name': '高档面料', 'qty': 500},
    ],
  },
  'selected_supplier': None,
}
f = describe_state_focus(c)
assert '脚轮' in (f.get('demand_scope') or '')
assert '面料' in (f.get('demand_scope') or '')
assert 'buyer' in (f.get('party_a') or '')
from commerce.choice_actions import post_quote_choices
w = post_quote_choices(
  case_id='case-x',
  split_plan=[
    {'sku': 'RM-CASTER-300', 'supplier_agent_id': 'supplier-a'},
    {'sku': 'RM-FABRIC-PRO', 'supplier_agent_id': 'supplier-b'},
  ],
)
assert '拆' in (w.get('prompt') or '') or '分单' in str(w)
print('THINKING_CHAIN_OK', f['state'], f['demand_scope'][:40])
PY
"""


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
    sftp = b.open_sftp()
    for rel in FILES:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()
    _, o, e = b.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 3; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b; " + CHECK,
        timeout=90,
        get_pty=True,
    )
    out = (o.read() + e.read()).decode("utf-8", "replace")
    sys.stdout.write(out + "\n")
    b.close()
    if "THINKING_CHAIN_OK" not in out:
        raise SystemExit(1)
    print("DEPLOY_THINKING_CHAIN_DONE", flush=True)


if __name__ == "__main__":
    main()
