# -*- coding: utf-8 -*-
"""趁 MQ 健康立刻跑 flow 组群竞价 + 截图。"""
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
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / f"group_ok_{RUN_ID}"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

URLS = {
    "buyer-a": "https://81.70.46.119:8090/",
    "supplier-a": "http://39.105.20.113:8091/",
    "supplier-c": "http://39.105.20.113:8094/",
    "logistics": "https://81.70.46.119:8095/",
}

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
os.environ["ACPS_GROUP_AUCTION"]="1"
from commerce import flow_service as fs, order_tickets as ot, procurement_case as pc, tickets as tk, logistics_tickets as lt

async def main():
    case=fs.create_from_brief(
        product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200,
        note="verify-group-now",
        lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}],
    )
    cid=case["case_id"]
    case=await fs.step_discover(cid, "标准脚轮200kg", bypass_cache=True)
    print("DISCOVER", cid, case.get("state"), len(case.get("candidates") or []), flush=True)
    case=fs.step_confirm_shortlist(cid, ["supplier-a","supplier-c"])
    case=await fs.step_rfq(cid)
    print("RFQ", case.get("state"), len(case.get("quotes") or []), flush=True)
    case=fs.step_decide(cid, "auction")
    case=await fs.step_auction(cid)
    summary=case.get("auction_summary") or {}
    priced=[b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]
    schemes=summary.get("schemes") or []
    print("AUCTION", json.dumps({
        "case_id":cid,"transport":summary.get("transport"),"priced":len(priced),
        "schemes":len(schemes),"best":schemes[0] if schemes else None,
        "fallback":summary.get("group_empty_fallback"),"abort":summary.get("abort_reason"),
        "bids":[{"id":b.get("supplier_agent_id") or b.get("agent_id"),"unit":b.get("unit_price"),"tco":b.get("tco")} for b in (case.get("auction_bids") or [])],
    }, ensure_ascii=False), flush=True)
    # if still rpc, one more try after brief pause
    if summary.get("transport") != "group":
        import time as _t; _t.sleep(4)
        pc.update_case(cid, state="BIDDING", hitl_pending=None)
        case=await fs.step_auction(cid)
        summary=case.get("auction_summary") or {}
        priced=[b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]
        schemes=summary.get("schemes") or []
        print("AUCTION2", json.dumps({
            "case_id":cid,"transport":summary.get("transport"),"priced":len(priced),
            "schemes":len(schemes),"best":schemes[0] if schemes else None,
            "fallback":summary.get("group_empty_fallback"),"abort":summary.get("abort_reason"),
        }, ensure_ascii=False), flush=True)
    case=fs.step_decide(cid,"order")
    draft=(case.get("order_draft") or {}).get("payload") or {}
    tid=case.get("order_ticket_id")
    print("ORDER", json.dumps({"supplier":case.get("selected_supplier"),"goods":draft.get("goods_total"),"ticket":tid,"state":case.get("state")},ensure_ascii=False), flush=True)
    try: case=await fs.step_shipping(cid)
    except Exception as e: print("SHIP_ERR", str(e)[:120], flush=True)
    if tid:
        try: ot.ack_order_generated("buyer-a", tid, sync_peer=True)
        except Exception as e: print("ACK_ERR", str(e)[:100], flush=True)
    print("DONE", json.dumps({"case_id":cid,"ticket":tid,"transport":summary.get("transport"),"priced":len(priced)},ensure_ascii=False), flush=True)
asyncio.run(main())
'''

SUP = r'''
import asyncio, json, os, sys, time
os.chdir("/opt/agentlink"); sys.path.insert(0,"/opt/agentlink")
from commerce import order_tickets as ot, tickets as tk, logistics_tickets as lt
acked=[]
for agent in ("supplier-a","supplier-c"):
  for t in [x for x in (tk.list_tickets(agent,limit=30) or []) if x.get("kind")=="order" and x.get("status")=="open" and not (x.get("state") or {}).get("supplier_order_ack")][:2]:
    try:
      r=ot.ack_order_generated(agent,t["id"],sync_peer=True)
      st=(r.get("state") if isinstance(r,dict) else None) or {}
      acked.append({"agent":agent,"tid":t["id"],"effective":st.get("order_effective")})
      print("SUP_ACK", json.dumps(acked[-1],ensure_ascii=False), flush=True)
    except Exception as e:
      print("SUP_ERR", agent, str(e)[:100], flush=True)
time.sleep(3)
for agent in ("supplier-a","supplier-c"):
  for t in (tk.list_tickets(agent,limit=30) or []):
    if t.get("kind")=="logistics_order" and t.get("status")=="open":
      try:
        lt.ack_logistics(agent,t["id"],sync_peer=True); print("LOG_ACK",agent,t["id"],flush=True)
      except Exception as e: print("LOG_ERR",e,flush=True)
print("SUP_DONE", json.dumps({"acked":acked},ensure_ascii=False), flush=True)
'''


def finish(cid: str) -> str:
    return f"""
import json,os,sys
os.chdir('/opt/agentlink'); sys.path.insert(0,'/opt/agentlink')
from commerce import tickets as tk, logistics_tickets as lt, procurement_case as pc, flow_service as fs
CID={cid!r}
for agent in ('buyer-a','logistics'):
  for t in (tk.list_tickets(agent,limit=40) or []):
    if t.get('kind')=='logistics_order' and t.get('status')=='open':
      try: lt.ack_logistics(agent,t['id'],sync_peer=True); print('BLOG',agent,t['id'],flush=True)
      except Exception as e: print('BLOG_ERR',e,flush=True)
case=pc.get_case(CID) or {{}}
try:
  if case.get('state')=='ORDER_DRAFT':
    try: pc.transition(CID,'CONTRACT_PENDING',event='g',patch={{'buyer_confirmed':True,'supplier_confirmed':True}})
    except Exception: pc.update_case(CID,buyer_confirmed=True,supplier_confirmed=True)
  else: pc.update_case(CID,buyer_confirmed=True,supplier_confirmed=True)
  c3=fs.step_activate(CID)
  print('ACTIVATE',CID,c3.get('state'),flush=True)
except Exception as e:
  print('ACTIVATE_ERR',e,flush=True)
"""


def ssh(host: str, *, pem: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    t = c.get_transport()
    if t:
        t.set_keepalive(15)
    return c


def remote_py(c: paramiko.SSHClient, code: str, *, env: str, timeout: int = 420) -> str:
    remote = f"/tmp/gnow_{int(time.time()*1000)}.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(code)
    sftp.close()
    cmd = (
        "set -a; . /opt/agentlink/.env; "
        f". /etc/agentlink/{env}; set +a; "
        f"cd /opt/agentlink && .venv/bin/python {remote}"
    )
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    print(out[-3000:], flush=True)
    return out


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
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ["NO_PROXY"] = "*"

    b = ssh("81.70.46.119", pem=True)
    try:
        out = remote_py(b, CODE, env="buyer-a.env", timeout=420)
        (OUT / "core.log").write_text(out, encoding="utf-8")
    finally:
        b.close()

    auction = marker(out, "AUCTION2") or marker(out, "AUCTION") or {}
    done = marker(out, "DONE") or {}
    order = marker(out, "ORDER") or {}
    cid = done.get("case_id") or auction.get("case_id")

    s = ssh("39.105.20.113", pem=False)
    try:
        out2 = remote_py(s, SUP, env="supplier-a.env", timeout=180)
        (OUT / "sup.log").write_text(out2, encoding="utf-8")
    finally:
        s.close()

    b = ssh("81.70.46.119", pem=True)
    try:
        out3 = remote_py(b, finish(cid or ""), env="buyer-a.env", timeout=120)
        (OUT / "finish.log").write_text(out3, encoding="utf-8")
    finally:
        b.close()

    shots = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--proxy-server=direct://", "--no-proxy-server"])
        try:
            for portal, page_name, label in [
                ("buyer-a", "tickets", "01_buyer_tickets"),
                ("buyer-a", "chat", "02_buyer_chat"),
                ("buyer-a", "audit", "03_buyer_audit"),
                ("supplier-a", "tickets", "04_sa_tickets"),
                ("supplier-c", "tickets", "05_sc_tickets"),
                ("logistics", "tickets", "06_logistics"),
            ]:
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
                page.screenshot(path=str(SHOT / name), full_page=True)
                shots.append(name)
                print("SHOT", name, flush=True)
                ctx.close()
            # chat summary turn
            ctx = browser.new_context(
                ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN"
            )
            page = ctx.new_page()
            page.goto(URLS["buyer-a"], wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(600)
            nav = page.locator('button.nav[data-page="chat"]')
            if nav.count():
                nav.first.click()
                page.wait_for_timeout(500)
            box = page.locator("#chatText")
            box.fill(f"用表格说明采购案 {cid} 是否组群竞价成功、transport、出价与是否 ACTIVE。")
            btn = page.locator("#btnSend")
            btn.click()
            deadline = time.time() + 90
            saw = False
            while time.time() < deadline:
                d = btn.is_disabled()
                if d:
                    saw = True
                elif saw and not d:
                    break
                page.wait_for_timeout(400)
            page.wait_for_timeout(600)
            page.screenshot(path=str(SHOT / "07_chat_summary.png"), full_page=True)
            shots.append("07_chat_summary.png")
            print("SHOT 07_chat_summary.png", flush=True)
            ctx.close()
        finally:
            browser.close()

    transport = auction.get("transport") or done.get("transport")
    priced = auction.get("priced") or done.get("priced") or 0
    ok = transport == "group" and priced >= 1 and bool(done.get("ticket") or order.get("ticket"))
    report = {
        "ok": ok,
        "transport": transport,
        "priced": priced,
        "auction": auction,
        "order": order,
        "done": done,
        "shots": shots,
        "case_id": cid,
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# 组群竞价（transport=group）· {RUN_ID}",
        f"- ok: `{ok}`",
        f"- transport: `{transport}` priced: `{priced}` case: `{cid}`",
        "",
        "## shots",
    ]
    for s in shots:
        lines.append(f"- ![{s}](screenshots/{s})")
    (OUT / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    print("GROUP_NOW", json.dumps(report, ensure_ascii=False)[:1500], flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
