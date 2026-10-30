# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = r"""
set -e
systemctl cat agentlink-supplier-a | head -40
echo '---'
for p in /opt/agentlink/.venv/bin/python /opt/agentlink/venv/bin/python /usr/bin/python3.11 /usr/bin/python3.10 /usr/local/bin/python3; do
  if [ -x "$p" ]; then echo FOUND $p; $p --version; PY=$p; break; fi
done
echo PY=${PY:-none}
if [ -z "${PY:-}" ]; then exit 2; fi
cd /opt/agentlink
PYTHONPATH=/opt/agentlink "$PY" - <<'PY'
import sys
print(sys.version)
from agents.supplier_common.negotiate import enrich_initial_quote, handle_bargain_round
import asyncio, yaml
from pathlib import Path
pol = yaml.safe_load(Path("/opt/agentlink/agents/supplier_a/policy.yaml").read_text())
q = enrich_initial_quote(
    {"unit_price": 20, "product": {"sku": "RM-CASTER-300", "quantity": 300, "name": "重型脚轮"}},
    pol,
)
assert q.get("policy_hints") is None and q.get("promotions_disclosed") is False, q
print("initial_ok", q.get("pricing_mode"), (q.get("note") or "")[:40])

async def t():
    st = {"agent_id": "supplier-a", "business_id": "t1"}
    env = {
        "schema_type": "agentlink.bargain_round",
        "business_id": "t1",
        "payload": {
            "quantity": 300,
            "product_name": "重型脚轮",
            "sku": "RM-CASTER-300",
            "previous_unit_price": 20,
            "goal_text": "有没有价格优惠",
            "need_freight": False,
        },
    }
    out = await handle_bargain_round(state=st, envelope=env, policy=pol)
    pay = out["outcome"]["envelope"]["payload"]
    assert pay.get("policy") and pay["policy"].get("hints"), pay.get("policy")
    print("bargain_ok", pay["policy"]["hints"][:1])
    print("reach", pay["policy"].get("reach_example"))

asyncio.run(t())
PY
systemctl is-active agentlink-supplier-a
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(REMOTE, timeout=90, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()


if __name__ == "__main__":
    main()
