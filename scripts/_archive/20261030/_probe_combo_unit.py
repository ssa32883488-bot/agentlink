# -*- coding: utf-8 -*-
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
REMOTE = r"""
cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, "/opt/agentlink")
from commerce.buyer_tools.service import BuyerToolService
from commerce.choice_actions import post_quote_choices
svc = BuyerToolService()
lines = svc._normalize_lines([], product_name="重型脚轮+高档面料", quantity=300)
assert len(lines) >= 2, lines
w = post_quote_choices(
    case_id="x",
    split_plan=[
        {"sku": "RM-CASTER-300", "supplier_agent_id": "supplier-a"},
        {"sku": "RM-FABRIC-PRO", "supplier_agent_id": "supplier-b"},
    ],
)
ids = [c["id"] for c in w["choices"]]
assert "split_orders" in ids, ids
print("UNIT_OK", [x["sku"] for x in lines], ids[:3], flush=True)
PY
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(REMOTE, timeout=60)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
