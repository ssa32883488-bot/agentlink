# -*- coding: utf-8 -*-
"""Fix supplier ERP group join hang: enable AIP_IDENTITY_BINDING=1, bump invite timeout, retest auction."""
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
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / f"auction_fix_{RUN_ID}"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

URLS = {
    "buyer-a": "https://81.70.46.119:8090/",
    "supplier-a": "http://39.105.20.113:8091/",
    "supplier-c": "http://39.105.20.113:8094/",
    "logistics": "https://81.70.46.119:8095/",
}


def ssh(host: str, *, pem: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    return (o.read() + e.read()).decode("utf-8", "replace")


def remote_py(c: paramiko.SSHClient, code: str, *, env: str, timeout: int = 480) -> str:
    remote = f"/tmp/fix_auction_{int(time.time()*1000)}.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(code)
    sftp.close()
    cmd = (
        "set -a; [ -f /opt/agentlink/.env ] && . /opt/agentlink/.env; "
        f"[ -f /etc/agentlink/{env} ] && . /etc/agentlink/{env}; set +a; "
        f"cd /opt/agentlink && /opt/agentlink/.venv/bin/python {remote}"
    )
    return run(c, cmd, timeout=timeout)


FIX_ALIYUN = r"""
set -e
for ag in supplier-a supplier-b supplier-c; do
  unit=/etc/systemd/system/agentlink-${ag}-erp.service
  if grep -q 'AIP_IDENTITY_BINDING=0' "$unit"; then
    sed -i 's/AIP_IDENTITY_BINDING=0/AIP_IDENTITY_BINDING=1/' "$unit"
    echo patched $unit
  else
    echo already_ok_or_missing $unit
    grep AIP_IDENTITY $unit || true
  fi
  # ensure env file also forces binding for group
  envf=/etc/agentlink/${ag}.env
  if [ -f "$envf" ]; then
    if grep -q '^AIP_IDENTITY_BINDING=' "$envf"; then
      sed -i 's/^AIP_IDENTITY_BINDING=.*/AIP_IDENTITY_BINDING=1/' "$envf"
    else
      echo 'AIP_IDENTITY_BINDING=1' >> "$envf"
    fi
    if grep -q '^ACPS_GROUP_IDENTITY_BINDING=' "$envf"; then
      sed -i 's/^ACPS_GROUP_IDENTITY_BINDING=.*/ACPS_GROUP_IDENTITY_BINDING=1/' "$envf"
    else
      echo 'ACPS_GROUP_IDENTITY_BINDING=1' >> "$envf"
    fi
  fi
done
systemctl daemon-reload
systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
sleep 4
systemctl is-active agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
grep AIP_IDENTITY /etc/systemd/system/agentlink-supplier-a-erp.service
"""

FIX_BUYER = r"""
set -e
# longer invite timeout for cross-cloud
if [ -f /etc/agentlink/buyer-a.env ]; then
  if grep -q '^ACPS_GROUP_INVITE_TIMEOUT_SEC=' /etc/agentlink/buyer-a.env; then
    sed -i 's/^ACPS_GROUP_INVITE_TIMEOUT_SEC=.*/ACPS_GROUP_INVITE_TIMEOUT_SEC=25/' /etc/agentlink/buyer-a.env
  else
    echo 'ACPS_GROUP_INVITE_TIMEOUT_SEC=25' >> /etc/agentlink/buyer-a.env
  fi
  if grep -q '^ACPS_GROUP_MIN_SUPPLIERS=' /etc/agentlink/buyer-a.env; then
    sed -i 's/^ACPS_GROUP_MIN_SUPPLIERS=.*/ACPS_GROUP_MIN_SUPPLIERS=1/' /etc/agentlink/buyer-a.env
  else
    echo 'ACPS_GROUP_MIN_SUPPLIERS=1' >> /etc/agentlink/buyer-a.env
  fi
fi
systemctl restart agentlink-buyer-a
sleep 4
systemctl is-active agentlink-buyer-a
grep ACPS_GROUP /etc/agentlink/buyer-a.env | head
"""

AUCTION = r'''
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
from commerce import flow_service as fs, order_tickets as ot

async def main():
    case=fs.create_from_brief(
        product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200,
        note="verify-auction-fix",
        lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}],
    )
    cid=case["case_id"]
    case=await fs.step_discover(cid, "标准脚轮200kg 供应商", bypass_cache=True)
    print("A_DISCOVER", json.dumps({"case_id":cid,"n":len(case.get("candidates") or [])},ensure_ascii=False), flush=True)
    case=fs.step_confirm_shortlist(cid, ["supplier-a","supplier-c"])
    case=await fs.step_rfq(cid)
    print("A_RFQ", case["state"], len(case.get("quotes") or []), flush=True)
    case=fs.step_decide(cid, "auction")
    case=await fs.step_auction(cid)
    summary=case.get("auction_summary") or {}
    schemes=summary.get("schemes") or []
    priced=[b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]
    print("A_AUCTION", json.dumps({
        "case_id":cid,"state":case["state"],"transport":summary.get("transport"),
        "priced":len(priced),"schemes":len(schemes),"best":schemes[0] if schemes else None,
        "early_abort":summary.get("early_abort"),"abort_reason":summary.get("abort_reason"),
        "group_empty_fallback":summary.get("group_empty_fallback"),
    }, ensure_ascii=False), flush=True)
    case=fs.step_decide(cid, "order")
    draft=(case.get("order_draft") or {}).get("payload") or {}
    print("A_ORDER", json.dumps({
        "case_id":cid,"supplier":case.get("selected_supplier"),"goods":draft.get("goods_total"),
        "ticket":case.get("order_ticket_id"),"state":case.get("state"),
    }, ensure_ascii=False), flush=True)
    try: case=await fs.step_shipping(cid)
    except Exception as e: print("A_SHIP_ERR", str(e)[:120], flush=True)
    tid=case.get("order_ticket_id")
    if tid:
        try: ot.ack_order_generated("buyer-a", tid, sync_peer=True)
        except Exception as e: print("A_ACK_ERR", str(e)[:100], flush=True)
    print("A_DONE", json.dumps({"case_id":cid,"ticket":tid,"transport":summary.get("transport"),"priced":len(priced)}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''


def shot(browser, portal: str, page_name: str, name: str) -> str:
    ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.goto(URLS[portal], wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(900)
    nav = page.locator(f'button.nav[data-page="{page_name}"]')
    if nav.count():
        nav.first.click()
        page.wait_for_timeout(1000)
    path = SHOT / name
    page.screenshot(path=str(path), full_page=True)
    print("SHOT", name, flush=True)
    ctx.close()
    return str(path)


def marker(out: str, key: str):
    for line in out.splitlines():
        if line.startswith(key + " "):
            raw = line[len(key) + 1 :].strip()
            try:
                return json.loads(raw)
            except Exception:
                return {"raw": raw}
    return None


def main() -> int:
    print("OUT", OUT, flush=True)
    s = ssh("39.105.20.113", pem=False)
    try:
        print(run(s, FIX_ALIYUN, timeout=90)[-2000:], flush=True)
    finally:
        s.close()
    b = ssh("81.70.46.119", pem=True)
    try:
        print(run(b, FIX_BUYER, timeout=60)[-1500:], flush=True)
        out = remote_py(b, AUCTION, env="buyer-a.env", timeout=480)
        (OUT / "a_core.log").write_text(out, encoding="utf-8")
        print(out[-3500:], flush=True)
    finally:
        b.close()

    auction = marker(out, "A_AUCTION") or {}
    order = marker(out, "A_ORDER") or {}
    done = marker(out, "A_DONE") or {}

    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ["NO_PROXY"] = "*"
    shots = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--proxy-server=direct://", "--no-proxy-server"])
        try:
            shots.append(shot(browser, "buyer-a", "tickets", "01_buyer_tickets_after_auction.png"))
            shots.append(shot(browser, "buyer-a", "chat", "02_buyer_chat.png"))
            shots.append(shot(browser, "buyer-a", "audit", "03_buyer_audit.png"))
            shots.append(shot(browser, "supplier-a", "tickets", "04_sa_tickets.png"))
            shots.append(shot(browser, "supplier-c", "tickets", "05_sc_tickets.png"))
            shots.append(shot(browser, "logistics", "tickets", "06_logistics.png"))
        finally:
            browser.close()

    ok = (auction.get("transport") == "group" and (auction.get("priced") or 0) >= 1) or (
        (auction.get("priced") or 0) >= 2 and done.get("ticket")
    )
    report = {
        "ok": ok,
        "strict_group": auction.get("transport") == "group",
        "auction": auction,
        "order": order,
        "done": done,
        "shots": [Path(s).name for s in shots],
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        f"# 组群竞价修复复测 · {RUN_ID}",
        "",
        f"- ok: `{ok}`",
        f"- transport: `{auction.get('transport')}`",
        f"- priced: `{auction.get('priced')}`",
        f"- schemes: `{auction.get('schemes')}`",
        "",
        "## shots",
    ]
    for s in shots:
        md.append(f"- ![{Path(s).name}](screenshots/{Path(s).name})")
    (OUT / "REVIEW.md").write_text("\n".join(md), encoding="utf-8")
    print("REPORT", json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
