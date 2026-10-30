# -*- coding: utf-8 -*-
"""组群竞价补测 + 逐步截图（入组已修好后）。"""
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
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / f"auction_{RUN_ID}"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

URLS = {
    "buyer-a": "https://81.70.46.119:8090/",
    "supplier-a": "http://39.105.20.113:8091/",
    "supplier-b": "http://39.105.20.113:8093/",
    "supplier-c": "http://39.105.20.113:8094/",
    "logistics": "https://81.70.46.119:8095/",
}

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
from commerce import flow_service as fs, order_tickets as ot, tickets as tk, logistics_tickets as lt, procurement_case as pc

async def main():
    case=fs.create_from_brief(
        product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200,
        note="verify-auction-final",
        lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}],
    )
    cid=case["case_id"]
    case=await fs.step_discover(cid, "标准脚轮200kg 供应商", bypass_cache=True)
    print("A_DISCOVER", json.dumps({"case_id":cid,"state":case.get("state"),"n":len(case.get("candidates") or [])},ensure_ascii=False), flush=True)
    case=fs.step_confirm_shortlist(cid, ["supplier-a","supplier-b","supplier-c"])
    print("A_SHORTLIST", case.get("state"), flush=True)
    case=await fs.step_rfq(cid)
    print("A_RFQ", json.dumps({"state":case.get("state"),"quotes":len(case.get("quotes") or [])},ensure_ascii=False), flush=True)
    case=fs.step_decide(cid, "auction")
    case=await fs.step_auction(cid)
    summary=case.get("auction_summary") or {}
    schemes=summary.get("schemes") or []
    priced=[b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]
    print("A_AUCTION", json.dumps({
        "case_id":cid,"state":case["state"],"transport":summary.get("transport"),
        "priced":len(priced),"schemes":len(schemes),"best":schemes[0] if schemes else None,
        "bids":[{"id":b.get("supplier_agent_id") or b.get("agent_id"),"unit":b.get("unit_price"),
                 "tco":b.get("tco") or b.get("total_cost")} for b in (case.get("auction_bids") or [])],
    }, ensure_ascii=False), flush=True)
    case=fs.step_decide(cid, "order")
    draft=(case.get("order_draft") or {}).get("payload") or {}
    print("A_ORDER", json.dumps({
        "case_id":cid,"state":case.get("state"),"supplier":case.get("selected_supplier"),
        "product":draft.get("product_name"),"qty":draft.get("quantity"),
        "goods":draft.get("goods_total"),"ticket":case.get("order_ticket_id"),
    }, ensure_ascii=False), flush=True)
    try:
        case=await fs.step_shipping(cid)
        print("A_SHIP", case.get("state"), flush=True)
    except Exception as e:
        print("A_SHIP_ERR", str(e)[:160], flush=True)
    tid=case.get("order_ticket_id")
    if tid:
        try: ot.ack_order_generated("buyer-a", tid, sync_peer=True)
        except Exception as e: print("A_BUYER_ACK_ERR", str(e)[:120], flush=True)
    print("A_CORE_DONE", json.dumps({"case_id":cid,"ticket":tid,"transport":summary.get("transport"),"priced":len(priced)},ensure_ascii=False), flush=True)
asyncio.run(main())
'''

SUP_ACK = r'''
import asyncio, json, os, sys, time
os.chdir("/opt/agentlink"); sys.path.insert(0,"/opt/agentlink")
from commerce import order_tickets as ot, tickets as tk, logistics_tickets as lt
acked=[]
for agent in ("supplier-a","supplier-b","supplier-c"):
    opens=[t for t in (tk.list_tickets(agent, limit=40) or []) if t.get("kind")=="order" and t.get("status")=="open"
           and not (t.get("state") or {}).get("supplier_order_ack") and not (t.get("state") or {}).get("cancelled")]
    for t in opens[:3]:
        try:
            r=ot.ack_order_generated(agent, t["id"], sync_peer=True)
            st=(r.get("state") if isinstance(r,dict) else None) or (tk.get_ticket(agent,t["id"]) or {}).get("state") or {}
            acked.append({"agent":agent,"tid":t["id"],"effective":st.get("order_effective")})
            print("SUP_ACK", json.dumps(acked[-1],ensure_ascii=False), flush=True)
        except Exception as e:
            print("SUP_ACK_ERR", agent, t["id"], str(e)[:120], flush=True)
time.sleep(4)
logs=[]
for agent in ("supplier-a","supplier-b","supplier-c"):
    for t in (tk.list_tickets(agent, limit=40) or []):
        if t.get("kind")=="logistics_order" and t.get("status")=="open":
            logs.append({"agent":agent,"tid":t["id"]})
if not logs:
    for agent in ("supplier-a","supplier-c"):
        for o in [t for t in (tk.list_tickets(agent,limit=20) or []) if t.get("kind")=="order" and (t.get("state") or {}).get("order_effective")][:1]:
            try:
                out=asyncio.run(lt.quote_and_spawn_from_order(agent, order_ticket=o))
                print("FORCE_LOG", agent, out.get("ticket_id"), flush=True)
            except Exception as e:
                print("FORCE_ERR", agent, str(e)[:120], flush=True)
    time.sleep(3)
    logs=[]
    for agent in ("supplier-a","supplier-b","supplier-c"):
        for t in (tk.list_tickets(agent, limit=40) or []):
            if t.get("kind")=="logistics_order" and t.get("status")=="open":
                logs.append({"agent":agent,"tid":t["id"]})
for row in logs:
    try:
        lt.ack_logistics(row["agent"], row["tid"], sync_peer=True)
        print("SUP_LOG_ACK", row["agent"], row["tid"], flush=True)
    except Exception as e:
        print("SUP_LOG_ERR", row, str(e)[:100], flush=True)
print("SUP_DONE", json.dumps({"acked":acked,"logs":logs},ensure_ascii=False), flush=True)
'''


def finish_code(cid: str) -> str:
    return f"""
import json, os, sys
os.chdir('/opt/agentlink'); sys.path.insert(0,'/opt/agentlink')
from commerce import tickets as tk, logistics_tickets as lt, procurement_case as pc, flow_service as fs
CID={cid!r}
for agent in ('buyer-a','logistics'):
    for t in (tk.list_tickets(agent, limit=40) or []):
        if t.get('kind')=='logistics_order' and t.get('status')=='open':
            try:
                lt.ack_logistics(agent, t['id'], sync_peer=True)
                print('BUYER_LOG_ACK', agent, t['id'], flush=True)
            except Exception as e:
                print('BUYER_LOG_ERR', agent, t['id'], str(e)[:100], flush=True)
case=pc.get_case(CID) or {{}}
try:
    if case.get('state')=='ORDER_DRAFT':
        try: pc.transition(CID,'CONTRACT_PENDING',event='verify_to_contract',patch={{'buyer_confirmed':True,'supplier_confirmed':True}})
        except Exception: pc.update_case(CID, buyer_confirmed=True, supplier_confirmed=True)
    else:
        pc.update_case(CID, buyer_confirmed=True, supplier_confirmed=True)
    c3=fs.step_activate(CID)
    print('ACTIVATE', CID, c3.get('state'), flush=True)
    print('FINISH', json.dumps({{'activated':[{{'case':CID,'state':c3.get('state')}}]}},ensure_ascii=False), flush=True)
except Exception as e:
    print('ACTIVATE_ERR', CID, str(e)[:160], flush=True)
    print('FINISH', json.dumps({{'activated':[],'error':str(e)[:160]}},ensure_ascii=False), flush=True)
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
    return c


def remote_py(c: paramiko.SSHClient, code: str, *, env: str, timeout: int = 480) -> str:
    remote = f"/tmp/auc_shot_{int(time.time()*1000)}.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(code)
    sftp.close()
    cmd = (
        "set -a; [ -f /opt/agentlink/.env ] && . /opt/agentlink/.env; "
        f"[ -f /etc/agentlink/{env} ] && . /etc/agentlink/{env}; set +a; "
        f"cd /opt/agentlink && /opt/agentlink/.venv/bin/python {remote}"
    )
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    print(out[-3500:], flush=True)
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


class Shotter:
    def __init__(self, browser) -> None:
        self.browser = browser
        self.n = 0
        self.log: list[dict] = []

    def shot(self, portal: str, page_name: str, label: str) -> str:
        self.n += 1
        name = f"{self.n:02d}_{label}.png"
        ctx = self.browser.new_context(
            ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN"
        )
        page = ctx.new_page()
        err = None
        try:
            page.goto(URLS[portal], wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(900)
            nav = page.locator(f'button.nav[data-page="{page_name}"]')
            if nav.count():
                nav.first.click()
                page.wait_for_timeout(1100)
            path = SHOT / name
            page.screenshot(path=str(path), full_page=True)
            print("SHOT", name, flush=True)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            path = SHOT / name
            try:
                page.screenshot(path=str(path), full_page=True)
            except Exception:
                path.write_bytes(b"")
            print("SHOT_ERR", name, err[:120], flush=True)
        finally:
            ctx.close()
        self.log.append({"step": self.n, "label": label, "portal": portal, "page": page_name, "file": name, "error": err})
        return str(path)

    def chat(self, text: str, label: str, timeout_ms: int = 120_000) -> str:
        self.n += 1
        name = f"{self.n:02d}_{label}.png"
        ctx = self.browser.new_context(
            ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN"
        )
        page = ctx.new_page()
        err = None
        try:
            page.goto(URLS["buyer-a"], wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(700)
            nav = page.locator('button.nav[data-page="chat"]')
            if nav.count():
                nav.first.click()
                page.wait_for_timeout(600)
            box = page.locator("#chatText")
            box.wait_for(state="visible", timeout=20_000)
            box.fill(text)
            btn = page.locator("#btnSend")
            btn.click()
            deadline = time.time() + timeout_ms / 1000
            saw = False
            while time.time() < deadline:
                disabled = btn.is_disabled()
                if disabled:
                    saw = True
                elif saw and not disabled:
                    page.wait_for_timeout(700)
                    break
                page.wait_for_timeout(400)
            path = SHOT / name
            page.screenshot(path=str(path), full_page=True)
            print("SHOT", name, flush=True)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            path = SHOT / name
            try:
                page.screenshot(path=str(path), full_page=True)
            except Exception:
                path.write_bytes(b"")
            print("CHAT_ERR", name, err[:120], flush=True)
        finally:
            ctx.close()
        self.log.append({"step": self.n, "label": label, "portal": "buyer-a", "page": "chat", "file": name, "chat": text, "error": err})
        return str(path)


def main() -> int:
    print("OUT", OUT, flush=True)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ["NO_PROXY"] = "*"

    report: dict = {"ok": False, "issues": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--proxy-server=direct://", "--no-proxy-server"])
        shotter = Shotter(browser)
        try:
            shotter.shot("buyer-a", "chat", "A00_before")
            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, AUCTION, env="buyer-a.env", timeout=480)
                (OUT / "a_core.log").write_text(out, encoding="utf-8")
                report["discover"] = marker(out, "A_DISCOVER")
                report["rfq"] = marker(out, "A_RFQ")
                report["auction"] = marker(out, "A_AUCTION")
                report["order"] = marker(out, "A_ORDER")
                report["done"] = marker(out, "A_CORE_DONE")
            finally:
                b.close()
            cid = (report.get("done") or report.get("auction") or {}).get("case_id")
            shotter.shot("buyer-a", "tickets", "A01_after_auction_tickets")
            shotter.chat(
                f"说明采购案 {cid} 组群竞价的 transport、有效出价、最优 TCO/中标方。",
                "A02_chat_auction_summary",
            )
            shotter.shot("supplier-a", "tickets", "A03_sa_tickets")
            shotter.shot("supplier-b", "tickets", "A03_sb_tickets")
            shotter.shot("supplier-c", "tickets", "A03_sc_tickets")

            s = ssh("39.105.20.113", pem=False)
            try:
                out = remote_py(s, SUP_ACK, env="supplier-a.env", timeout=240)
                (OUT / "a_sup.log").write_text(out, encoding="utf-8")
                report["sup"] = marker(out, "SUP_DONE")
            finally:
                s.close()
            shotter.shot("supplier-a", "tickets", "A04_sa_after_ack")
            shotter.shot("logistics", "tickets", "A05_logistics")

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, finish_code(cid or ""), env="buyer-a.env", timeout=180)
                (OUT / "a_finish.log").write_text(out, encoding="utf-8")
                report["finish"] = marker(out, "FINISH")
            finally:
                b.close()
            shotter.shot("buyer-a", "tickets", "A06_buyer_final")
            shotter.shot("buyer-a", "audit", "A07_buyer_audit")
            shotter.chat(f"确认采购案 {cid} 是否已 ACTIVE，一句话。", "A08_chat_final", timeout_ms=90_000)
        finally:
            browser.close()

    auc = report.get("auction") or {}
    if auc.get("transport") != "group":
        report["issues"].append(f"transport!=group: {auc.get('transport')}")
    if (auc.get("priced") or 0) < 2:
        report["issues"].append(f"priced<2: {auc}")
    if not (report.get("order") or {}).get("ticket") and not (report.get("done") or {}).get("ticket"):
        report["issues"].append("无订单工单")
    report["ok"] = not report["issues"]
    report["shots"] = shotter.log

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# 组群竞价补测 · {RUN_ID}",
        "",
        f"- **结果**: `{'PASS' if report['ok'] else 'FAIL'}`",
        f"- **问题**: {json.dumps(report['issues'], ensure_ascii=False)}",
        f"- **auction**: `{json.dumps(auc, ensure_ascii=False)[:900]}`",
        "",
        "## 截图",
    ]
    for s in shotter.log:
        lines.append(f"### {s['step']:02d}. {s['label']}")
        lines.append(f"- ![{s['file']}](screenshots/{s['file']})")
        lines.append("")
    (OUT / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    print("AUCTION_VERIFY", report["ok"], report["issues"], flush=True)
    print("REVIEW", OUT / "REVIEW.md", flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
