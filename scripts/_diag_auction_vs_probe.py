# -*- coding: utf-8 -*-
"""Compare bare group probe vs post-RFQ group invite on buyer host."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

CODE = r'''
import asyncio, json, os, sys, traceback
os.chdir("/opt/agentlink"); sys.path.insert(0,"/opt/agentlink")
from commerce.env_loader import load_dotenv
load_dotenv()
for f in ("/etc/agentlink/buyer-a.env",):
    if os.path.isfile(f):
        for line in open(f, encoding="utf-8"):
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,v=line.split("=",1); os.environ[k.strip()] = v.strip().strip('"')
os.environ["ACPS_GROUP_INVITE_TIMEOUT_SEC"]="25"
os.environ["ACPS_GROUP_MIN_SUPPLIERS"]="1"
from commerce import group_mq as gm, flow_service as fs

ENV = {
    "schema_type":"agentlink.blind_bid","schema_version":"1.0","business_id":"diag",
    "payload":{"auction_id":"diag","product_name":"标准脚轮200kg","sku":"RM-CASTER-200","quantity":500,"sealed":True},
}

async def probe(tag):
    try:
        out = await gm.run_group_blind_auction(
            leader_aic=os.environ.get("BUYER_A_AIC",""),
            leader_agent_id="buyer-a",
            member_agent_ids=["supplier-a","supplier-c"],
            bid_envelope=ENV,
            with_tco=False,
            dissolve=True,
        )
        print(tag, json.dumps({
            "abort":out.get("early_abort"),"reason":out.get("abort_reason"),
            "invite_ms":out.get("invite_elapsed_ms"),
            "members":out.get("members"),
            "priced":len([b for b in (out.get("bids") or []) if b.get("unit_price") is not None]),
        }, ensure_ascii=False), flush=True)
    except Exception:
        print(tag, "EXC", flush=True)
        traceback.print_exc()

async def main():
    print("STEP1 bare probe", flush=True)
    await probe("BARE")
    print("STEP2 rfq then probe", flush=True)
    case=fs.create_from_brief(product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200,
        note="diag-rfq-group", lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}])
    cid=case["case_id"]
    case=await fs.step_discover(cid, "标准脚轮200kg", bypass_cache=True)
    case=fs.step_confirm_shortlist(cid, ["supplier-a","supplier-c"])
    case=await fs.step_rfq(cid)
    print("RFQ_DONE", case.get("state"), len(case.get("quotes") or []), flush=True)
    await probe("AFTER_RFQ")
    print("STEP3 step_auction", flush=True)
    case=fs.step_decide(cid, "auction")
    case=await fs.step_auction(cid)
    summary=case.get("auction_summary") or {}
    print("FLOW", json.dumps({
        "transport":summary.get("transport"),
        "priced":len([b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]),
        "fallback":summary.get("group_empty_fallback"),
        "abort":summary.get("abort_reason"),
    }, ensure_ascii=False), flush=True)

asyncio.run(main())
'''


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
    remote = "/tmp/diag_auc_probe.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(CODE)
    sftp.close()
    cmd = (
        "set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a; "
        f"cd /opt/agentlink && .venv/bin/python {remote}"
    )
    _, o, e = c.exec_command(cmd, timeout=420, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace")[-6000:])
    c.close()


if __name__ == "__main__":
    main()
