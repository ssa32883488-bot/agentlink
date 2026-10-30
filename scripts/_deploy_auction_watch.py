# -*- coding: utf-8 -*-
"""Deploy auction-watch UI + pending_choices-on-auction backend to buyer/supplier clouds."""
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
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        sftp.put(str(ROOT / rel), remote)
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
        "agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; "
        "sleep 3; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b; "
        "grep -n 'auctionWatch\\|renderAuctionWatch\\|post_auction_scheme_choices\\|collabTimeline' "
        "/opt/agentlink/ui/static/index.html /opt/agentlink/ui/static/app.js "
        "/opt/agentlink/commerce/choice_actions.py | head -30",
    )
    # Inject a BID_REVIEW fixture case and verify API shape for the watch page
    run(
        b,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "import json, os, sys\n"
        "sys.path.insert(0, '/opt/agentlink')\n"
        "os.chdir('/opt/agentlink')\n"
        "from commerce.env_loader import load_dotenv\n"
        "load_dotenv()\n"
        "from commerce import procurement_case as pc\n"
        "from commerce.choice_actions import post_auction_scheme_choices\n"
        "case = pc.create_case(brief={'product_name':'重型脚轮','quantity':500}, created_by='buyer-a')\n"
        "cid = case['case_id']\n"
        "schemes = [\n"
        "  {'supplier_agent_id':'supplier-b','unit_price':11.8,'freight':200,'tco':6100},\n"
        "  {'supplier_agent_id':'supplier-a','unit_price':12.5,'freight':150,'tco':6400},\n"
        "]\n"
        "bids = [\n"
        "  {'supplier_agent_id':'supplier-a','unit_price':12.5,'tco':6400},\n"
        "  {'supplier_agent_id':'supplier-b','unit_price':11.8,'tco':6100},\n"
        "  {'supplier_agent_id':'supplier-c','error':'timeout'},\n"
        "]\n"
        "widget = post_auction_scheme_choices(case_id=cid, schemes=schemes, bids=bids)\n"
        "assert widget and widget.get('choices'), widget\n"
        "pc.update_case(cid,\n"
        "  state='BID_REVIEW',\n"
        "  shortlist=[{'agent_id':'supplier-a'},{'agent_id':'supplier-b'},{'agent_id':'supplier-c'}],\n"
        "  auction_bids=bids,\n"
        "  auction_summary={'transport':'group','offers_got':2,'schemes':schemes,'ranked':bids[:2]},\n"
        "  pending_choices=widget,\n"
        "  hitl_pending={'phase':'bid_review','prompt':'组群竞价+物流TCO方案（仅采购可见）'},\n"
        ")\n"
        "got = pc.get_case(cid)\n"
        "ok = (\n"
        "  got['state']=='BID_REVIEW'\n"
        "  and got.get('auction_summary',{}).get('schemes')\n"
        "  and got.get('pending_choices',{}).get('choices')\n"
        ")\n"
        "print('FIXTURE', cid, 'choices', len(got['pending_choices']['choices']), 'PASS' if ok else 'FAIL', flush=True)\n"
        "print(json.dumps({'case_id':cid,'n_schemes':len(got['auction_summary']['schemes']),\n"
        "  'n_choices':len(got['pending_choices']['choices']),\n"
        "  'labels':[c.get('label') for c in got['pending_choices']['choices']]}, ensure_ascii=False), flush=True)\n"
        "raise SystemExit(0 if ok else 1)\n"
        "PY",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, ["ui/static/app.js", "ui/static/index.html", "ui/static/styles.css"])
    run(
        s,
        "systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; "
        "sleep 2; systemctl is-active agentlink-ui-supplier-a",
    )
    s.close()
    print("DEPLOY_AUCTION_WATCH_DONE", flush=True)


if __name__ == "__main__":
    main()
