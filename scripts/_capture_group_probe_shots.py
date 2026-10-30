# -*- coding: utf-8 -*-
"""Capture screenshots immediately after a successful group-plane probe (no RFQ)."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import paramiko
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / f"group_plane_{RUN_ID}"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

CODE = r'''
import asyncio, json, os, sys
os.chdir("/opt/agentlink"); sys.path.insert(0,"/opt/agentlink")
from commerce.env_loader import load_dotenv
load_dotenv()
for f in ("/etc/agentlink/buyer-a.env",):
    if os.path.isfile(f):
        for line in open(f, encoding="utf-8"):
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,v=line.split("=",1); os.environ[k.strip()] = v.strip().strip('"')
os.environ["ACPS_GROUP_INVITE_TIMEOUT_SEC"]="30"
os.environ["ACPS_GROUP_MIN_SUPPLIERS"]="1"
from commerce import group_mq as gm
async def main():
    out=await gm.run_group_blind_auction(
        leader_aic=os.environ.get("BUYER_A_AIC",""), leader_agent_id="buyer-a",
        member_agent_ids=["supplier-a","supplier-c"],
        bid_envelope={"schema_type":"agentlink.blind_bid","schema_version":"1.0","business_id":"plane",
            "payload":{"auction_id":"plane","product_name":"标准脚轮200kg","sku":"RM-CASTER-200","quantity":500,"sealed":True}},
        with_tco=False, dissolve=True)
    joined=[m for m in (out.get("members") or []) if m.get("status")=="joined"]
    priced=[b for b in (out.get("bids") or []) if b.get("unit_price") is not None]
    print("PLANE", json.dumps({
        "transport":"group" if joined and not out.get("early_abort") else "failed",
        "joined":[m.get("agent_id") for m in joined],
        "invite_ms":out.get("invite_elapsed_ms"),
        "priced":len(priced),
        "bids":[{"id":b.get("supplier_agent_id"),"unit":b.get("unit_price")} for b in priced],
        "abort":out.get("abort_reason"),
        "members":out.get("members"),
    }, ensure_ascii=False), flush=True)
asyncio.run(main())
'''


def main() -> int:
    print("OUT", OUT, flush=True)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ["NO_PROXY"] = "*"

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = s.exec_command(
        "systemctl restart agentlink-supplier-a-erp agentlink-supplier-c-erp; sleep 3; systemctl is-active agentlink-supplier-a-erp",
        timeout=45,
        get_pty=True,
    )
    print((o.read() + e.read()).decode()[-200:], flush=True)
    s.close()

    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    remote = f"/tmp/plane_{int(time.time()*1000)}.py"
    sftp = b.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(CODE)
    sftp.close()
    _, o, e = b.exec_command(
        "set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a; "
        f"cd /opt/agentlink && .venv/bin/python {remote}",
        timeout=120,
        get_pty=True,
    )
    out = (o.read() + e.read()).decode("utf-8", "replace")
    print(out[-2000:], flush=True)
    b.close()
    plane = None
    for line in out.splitlines():
        if line.startswith("PLANE "):
            plane = json.loads(line[6:])
    (OUT / "plane.json").write_text(json.dumps(plane, ensure_ascii=False, indent=2), encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--proxy-server=direct://", "--no-proxy-server"])
        try:
            for portal, page, name in [
                ("https://81.70.46.119:8090/", "chat", "01_buyer_chat.png"),
                ("https://81.70.46.119:8090/", "tickets", "02_buyer_tickets.png"),
                ("http://39.105.20.113:8091/", "tickets", "03_sa_tickets.png"),
                ("http://39.105.20.113:8094/", "tickets", "04_sc_tickets.png"),
            ]:
                ctx = browser.new_context(
                    ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN"
                )
                pg = ctx.new_page()
                pg.goto(portal, wait_until="domcontentloaded", timeout=60_000)
                pg.wait_for_timeout(700)
                nav = pg.locator(f'button.nav[data-page="{page}"]')
                if nav.count():
                    nav.first.click()
                    pg.wait_for_timeout(900)
                pg.screenshot(path=str(SHOT / name), full_page=True)
                print("SHOT", name, flush=True)
                ctx.close()
        finally:
            browser.close()

    ok = bool(plane) and plane.get("transport") == "group" and (plane.get("priced") or 0) >= 1
    (OUT / "REVIEW.md").write_text(
        f"# Group plane probe · {RUN_ID}\n\n- ok: `{ok}`\n- data: `{json.dumps(plane, ensure_ascii=False)}`\n",
        encoding="utf-8",
    )
    # append to INDEX
    idx = ROOT / "docs" / "evidence" / "verify_ui_shots" / "INDEX.md"
    if idx.is_file():
        idx.write_text(
            idx.read_text(encoding="utf-8")
            + f"\n## 4. 组群平面探针（直连 MQ，无 RFQ）\n\n"
            f"- 目录：[`group_plane_{RUN_ID}/`](./group_plane_{RUN_ID}/)\n"
            f"- ok: `{ok}` transport=`{plane.get('transport') if plane else None}` "
            f"priced=`{(plane or {}).get('priced')}` joined=`{(plane or {}).get('joined')}`\n",
            encoding="utf-8",
        )
    print("PLANE_RESULT", ok, plane, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
