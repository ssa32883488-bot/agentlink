# -*- coding: utf-8 -*-
"""单次重试：等 MQ 冷静后跑组群竞价，要求 transport=group，并截图。"""
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
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / f"auction_group_{RUN_ID}"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

URLS = {
    "buyer-a": "https://81.70.46.119:8090/",
    "supplier-a": "http://39.105.20.113:8091/",
    "supplier-c": "http://39.105.20.113:8094/",
    "logistics": "https://81.70.46.119:8095/",
}

CODE = r'''
import asyncio, json, os, sys, time
os.chdir("/opt/agentlink"); sys.path.insert(0,"/opt/agentlink")
from commerce.env_loader import load_dotenv
load_dotenv()
for f in ("/etc/agentlink/buyer-a.env",):
    if os.path.isfile(f):
        for line in open(f, encoding="utf-8"):
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,v=line.split("=",1); os.environ[k.strip()] = v.strip().strip('"')
# force generous invite
os.environ["ACPS_GROUP_INVITE_TIMEOUT_SEC"]="30"
os.environ["ACPS_GROUP_MIN_SUPPLIERS"]="1"
os.environ["ACPS_GROUP_AUCTION"]="1"
from commerce import flow_service as fs, order_tickets as ot

async def main():
    time.sleep(3)
    case=fs.create_from_brief(
        product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200,
        note="verify-group-retry",
        lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}],
    )
    cid=case["case_id"]
    case=await fs.step_discover(cid, "标准脚轮200kg", bypass_cache=True)
    case=fs.step_confirm_shortlist(cid, ["supplier-a","supplier-c"])
    case=await fs.step_rfq(cid)
    print("RFQ", case.get("state"), len(case.get("quotes") or []), flush=True)
    case=fs.step_decide(cid, "auction")
    # retry auction once if rpc fallback
    case=await fs.step_auction(cid)
    summary=case.get("auction_summary") or {}
    if summary.get("transport") != "group" or summary.get("group_empty_fallback"):
        print("RETRY_GROUP", summary.get("transport"), summary.get("abort_reason"), flush=True)
        time.sleep(5)
        # reset to BIDDING if needed
        from commerce import procurement_case as pc
        pc.update_case(cid, state="BIDDING", hitl_pending=None)
        case=await fs.step_auction(cid)
        summary=case.get("auction_summary") or {}
    priced=[b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]
    schemes=summary.get("schemes") or []
    print("A_AUCTION", json.dumps({
        "case_id":cid,"transport":summary.get("transport"),"priced":len(priced),
        "schemes":len(schemes),"best":schemes[0] if schemes else None,
        "fallback":summary.get("group_empty_fallback"),"abort":summary.get("abort_reason"),
        "bids":[{"id":b.get("supplier_agent_id") or b.get("agent_id"),"unit":b.get("unit_price"),
                 "tco":b.get("tco")} for b in (case.get("auction_bids") or [])],
    }, ensure_ascii=False), flush=True)
    case=fs.step_decide(cid,"order")
    draft=(case.get("order_draft") or {}).get("payload") or {}
    tid=case.get("order_ticket_id")
    if tid:
        try: ot.ack_order_generated("buyer-a", tid, sync_peer=True)
        except Exception as e: print("ACK_ERR", e, flush=True)
    print("A_DONE", json.dumps({"case_id":cid,"ticket":tid,"supplier":case.get("selected_supplier"),
        "goods":draft.get("goods_total"),"transport":summary.get("transport")}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''


def main() -> int:
    print("OUT", OUT, flush=True)
    print("cool_down 8s...", flush=True)
    time.sleep(8)

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
    remote = f"/tmp/retry_group_{int(time.time()*1000)}.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(CODE)
    sftp.close()
    cmd = (
        "set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a; "
        f"cd /opt/agentlink && /opt/agentlink/.venv/bin/python {remote}"
    )
    _, o, e = c.exec_command(cmd, timeout=480, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    (OUT / "core.log").write_text(out, encoding="utf-8")
    print(out[-4000:], flush=True)
    c.close()

    auction = None
    done = None
    for line in out.splitlines():
        if line.startswith("A_AUCTION "):
            try:
                auction = json.loads(line[len("A_AUCTION ") :])
            except Exception:
                auction = {"raw": line}
        if line.startswith("A_DONE "):
            try:
                done = json.loads(line[len("A_DONE ") :])
            except Exception:
                done = {"raw": line}

    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ["NO_PROXY"] = "*"
    shots = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--proxy-server=direct://", "--no-proxy-server"])
        try:
            for i, (portal, page_name, label) in enumerate(
                [
                    ("buyer-a", "tickets", "01_buyer_tickets"),
                    ("buyer-a", "chat", "02_buyer_chat"),
                    ("buyer-a", "audit", "03_buyer_audit"),
                    ("supplier-a", "tickets", "04_sa_tickets"),
                    ("supplier-c", "tickets", "05_sc_tickets"),
                    ("logistics", "tickets", "06_logistics"),
                ],
                1,
            ):
                ctx = browser.new_context(
                    ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN"
                )
                page = ctx.new_page()
                page.goto(URLS[portal], wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(800)
                nav = page.locator(f'button.nav[data-page="{page_name}"]')
                if nav.count():
                    nav.first.click()
                    page.wait_for_timeout(1000)
                name = f"{label}.png"
                path = SHOT / name
                page.screenshot(path=str(path), full_page=True)
                shots.append(name)
                print("SHOT", name, flush=True)
                ctx.close()
        finally:
            browser.close()

    transport = (auction or {}).get("transport")
    priced = (auction or {}).get("priced") or 0
    ok = transport == "group" and priced >= 1 and bool((done or {}).get("ticket"))
    report = {"ok": ok, "auction": auction, "done": done, "shots": shots}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# 组群竞价重试 · {RUN_ID}",
        f"- ok: `{ok}`",
        f"- transport: `{transport}` priced: `{priced}`",
        "",
        "## shots",
    ]
    for s in shots:
        lines.append(f"- ![{s}](screenshots/{s})")
    (OUT / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    print("RETRY_RESULT", json.dumps(report, ensure_ascii=False)[:1200], flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
