# -*- coding: utf-8 -*-
"""Deploy combo-demand discover/RFQ/split-after-quote + shortlist UI."""
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

FILES = [
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/static/styles.css",
    "commerce/choice_actions.py",
    "commerce/flow_service.py",
    "commerce/chat_buyer_wit.py",
    "commerce/buyer_tools/schemas.py",
    "commerce/buyer_tools/service.py",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", "replace")


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
    put(b, FILES)
    run(
        b,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b; sleep 3; "
        "systemctl is-active agentlink-buyer-a agentlink-ui-buyer-a; "
        "grep -n '组合需求\\|lines_json\\|按覆盖分两单\\|trade_name' "
        "/opt/agentlink/commerce/chat_buyer_wit.py "
        "/opt/agentlink/commerce/choice_actions.py "
        "/opt/agentlink/ui/static/app.js | head -25",
    )
    # unit: normalize lines + post_quote split
    run(
        b,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "import sys; sys.path.insert(0,'/opt/agentlink')\n"
        "from commerce.buyer_tools.service import BuyerToolService\n"
        "from commerce.choice_actions import post_quote_choices\n"
        "svc=BuyerToolService()\n"
        "lines=svc._normalize_lines([], product_name='重型脚轮+高档面料', quantity=300)\n"
        "assert len(lines)>=2, lines\n"
        "w=post_quote_choices(case_id='x', split_plan=[\n"
        " {'sku':'RM-CASTER-300','supplier_agent_id':'supplier-a'},\n"
        " {'sku':'RM-FABRIC-PRO','supplier_agent_id':'supplier-b'}])\n"
        "ids=[c['id'] for c in w['choices']]\n"
        "assert 'split_orders' in ids, ids\n"
        "print('UNIT_OK', [x['sku'] for x in lines], ids[:3])\n"
        "PY",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, ["ui/static/app.js", "ui/static/index.html", "ui/static/styles.css"])
    run(s, "systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; sleep 2; systemctl is-active agentlink-ui-supplier-a")
    s.close()
    print("DEPLOY_COMBO_RFQ_DONE", flush=True)


if __name__ == "__main__":
    main()
