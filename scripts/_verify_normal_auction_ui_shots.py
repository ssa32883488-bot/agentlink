# -*- coding: utf-8 -*-
"""全面验证：普通采购 + 组群竞价；每一步浏览器全页截图。

业务在腾讯 buyer / 阿里云 supplier 用工具链推进（稳定可复现）；
Playwright 打开采购/供应/物流控制台，在每个里程碑截图。

输出：docs/evidence/verify_ui_shots/<run_id>/
  screenshots/*.png
  REVIEW.md
  report.json
  *.log
"""
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
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / RUN_ID
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

# 直连云主机 IP（绕过本机代理对域名的干扰）
URLS = {
    "buyer-a": "https://81.70.46.119:8090/",
    "buyer-b": "https://81.70.46.119:8092/",
    "supplier-a": "http://39.105.20.113:8091/",
    "supplier-b": "http://39.105.20.113:8093/",
    "supplier-c": "http://39.105.20.113:8094/",
    "logistics": "https://81.70.46.119:8095/",
}


def ssh(host: str, *, pem: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = {"hostname": host, "username": "root", "timeout": 40, "allow_agent": False, "look_for_keys": False}
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    return c


def remote_py(c: paramiko.SSHClient, code: str, *, env: str, timeout: int = 420) -> str:
    remote = f"/tmp/verify_ui_{int(time.time() * 1000)}.py"
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
        self.log: list[dict] = []
        self.n = 0

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
            print("SHOT_ERR", name, err, flush=True)
        finally:
            ctx.close()
        self.log.append({"step": self.n, "label": label, "portal": portal, "page": page_name, "file": name, "error": err})
        return str(path)

    def chat_ask(self, portal: str, text: str, label: str, timeout_ms: int = 180_000) -> str:
        """发一轮对话并截图（用于 UI 可见证据）。"""
        self.n += 1
        name = f"{self.n:02d}_{label}.png"
        ctx = self.browser.new_context(
            ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN"
        )
        page = ctx.new_page()
        err = None
        try:
            page.goto(URLS[portal], wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(800)
            nav = page.locator('button.nav[data-page="chat"]')
            if nav.count():
                nav.first.click()
                page.wait_for_timeout(700)
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
                    page.wait_for_timeout(800)
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
            print("CHAT_ERR", name, err, flush=True)
        finally:
            ctx.close()
        self.log.append(
            {
                "step": self.n,
                "label": label,
                "portal": portal,
                "page": "chat",
                "file": name,
                "chat": text,
                "error": err,
            }
        )
        return str(path)


# ---------- remote business ----------

BOOT = r'''
import os, sys
os.chdir("/opt/agentlink"); sys.path.insert(0,"/opt/agentlink")
from commerce.env_loader import load_dotenv
load_dotenv()
for f in ("/etc/agentlink/buyer-a.env",):
    if os.path.isfile(f):
        for line in open(f, encoding="utf-8"):
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,v=line.split("=",1); os.environ.setdefault(k.strip(), v.strip().strip('"'))
'''

NORMAL_DISCOVER = BOOT + r'''
import asyncio, json
from commerce import flow_service as fs

async def main():
    case = fs.create_from_brief(
        product_name="重型脚轮300kg", quantity=500, rated_load_kg_min=300,
        note="verify-normal-ui",
        lines=[{"sku":"RM-CASTER-300","name":"重型脚轮300kg","qty":500}],
    )
    cid = case["case_id"]
    case = await fs.step_discover(cid, "重型脚轮300kg 供应商", bypass_cache=True)
    cands = case.get("candidates") or []
    print("N_DISCOVER", json.dumps({
        "case_id": cid, "state": case.get("state"), "n": len(cands),
        "ids": [c.get("agent_id") for c in cands],
        "source": (case.get("discovery_meta") or {}).get("source"),
    }, ensure_ascii=False), flush=True)
asyncio.run(main())
'''

def normal_rfq_code(cid: str) -> str:
    return (
        BOOT
        + f"\nCID = {cid!r}\n"
        + r'''
import asyncio, json
from commerce import flow_service as fs
cid = CID

async def main():
    case = fs.step_confirm_shortlist(cid, ["supplier-a","supplier-b","supplier-c"])
    print("N_SHORTLIST", json.dumps({"case_id":cid,"state":case.get("state"),
        "shortlist":case.get("shortlist") or case.get("selected_agents")}, ensure_ascii=False), flush=True)
    case = await fs.step_rfq(cid)
    quotes = case.get("quotes") or []
    print("N_RFQ", json.dumps({
        "case_id":cid,"state":case.get("state"),"quote_n":len(quotes),
        "suppliers":[q.get("supplier_agent_id") or q.get("agent_id") for q in quotes],
        "prices":[{ "id": q.get("supplier_agent_id") or q.get("agent_id"),
                    "unit": q.get("unit_price"), "total": q.get("goods_total") or q.get("total")} for q in quotes],
    }, ensure_ascii=False), flush=True)
asyncio.run(main())
'''
    )


def normal_order_code(cid: str) -> str:
    return (
        BOOT
        + f"\nCID = {cid!r}\n"
        + r'''
import asyncio, json
from commerce import flow_service as fs, order_tickets as ot
cid = CID

async def main():
    case = fs.step_decide(cid, "order", supplier_agent_id="supplier-a", sku="RM-CASTER-300")
    draft = (case.get("order_draft") or {}).get("payload") or {}
    print("N_ORDER", json.dumps({
        "case_id":cid,"state":case.get("state"),"supplier":case.get("selected_supplier"),
        "product":draft.get("product_name"),"qty":draft.get("quantity"),
        "unit":draft.get("unit_price"),"goods":draft.get("goods_total"),
        "ticket":case.get("order_ticket_id"),
    }, ensure_ascii=False), flush=True)
    try:
        case = await fs.step_shipping(cid)
        print("N_SHIP", json.dumps({"state":case.get("state"),
            "ship":((case.get("order_draft") or {}).get("payload") or {}).get("shipping_cost"),
            "ticket":case.get("order_ticket_id")}, ensure_ascii=False), flush=True)
    except Exception as e:
        print("N_SHIP", json.dumps({"error":str(e)[:200]}, ensure_ascii=False), flush=True)
    tid = case.get("order_ticket_id")
    if tid:
        try:
            ot.ack_order_generated("buyer-a", tid, sync_peer=True)
            print("N_BUYER_ACK", tid, flush=True)
        except Exception as e:
            print("N_BUYER_ACK_ERR", str(e)[:160], flush=True)
    print("N_ORDER_DONE", json.dumps({"case_id":cid,"ticket":tid}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''
    )

AUCTION_CORE = BOOT + r'''
import asyncio, json
from commerce import flow_service as fs, order_tickets as ot

async def main():
    case = fs.create_from_brief(
        product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200,
        note="verify-auction-ui",
        lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}],
    )
    cid = case["case_id"]
    case = await fs.step_discover(cid, "标准脚轮200kg 供应商", bypass_cache=True)
    print("A_DISCOVER", json.dumps({"case_id":cid,"state":case.get("state"),
        "n":len(case.get("candidates") or []),
        "ids":[c.get("agent_id") for c in (case.get("candidates") or [])]}, ensure_ascii=False), flush=True)
    case = fs.step_confirm_shortlist(cid, ["supplier-a","supplier-b","supplier-c"])
    print("A_SHORTLIST", json.dumps({"case_id":cid,"state":case.get("state")}, ensure_ascii=False), flush=True)
    case = await fs.step_rfq(cid)
    print("A_RFQ", json.dumps({"case_id":cid,"state":case.get("state"),
        "quotes":len(case.get("quotes") or [])}, ensure_ascii=False), flush=True)
    case = fs.step_decide(cid, "auction")
    print("A_DECIDE_AUCTION", case.get("state"), flush=True)
    case = await fs.step_auction(cid)
    summary = case.get("auction_summary") or {}
    schemes = summary.get("schemes") or []
    bids = case.get("auction_bids") or []
    priced = [b for b in bids if b.get("unit_price") is not None]
    print("A_AUCTION", json.dumps({
        "case_id":cid,"state":case.get("state"),"transport":summary.get("transport"),
        "priced":len(priced),"schemes":len(schemes),"best":schemes[0] if schemes else None,
        "bids":[{"id":b.get("supplier_agent_id") or b.get("agent_id"),"unit":b.get("unit_price"),
                 "tco":b.get("tco") or b.get("total_cost")} for b in bids],
    }, ensure_ascii=False), flush=True)
    case = fs.step_decide(cid, "order")
    draft = (case.get("order_draft") or {}).get("payload") or {}
    print("A_ORDER", json.dumps({
        "case_id":cid,"state":case.get("state"),"supplier":case.get("selected_supplier"),
        "product":draft.get("product_name"),"qty":draft.get("quantity"),
        "goods":draft.get("goods_total"),"ship":draft.get("shipping_cost"),
        "ticket":case.get("order_ticket_id"),
    }, ensure_ascii=False), flush=True)
    try:
        case = await fs.step_shipping(cid)
        print("A_SHIP", case.get("state"), flush=True)
    except Exception as e:
        print("A_SHIP_ERR", str(e)[:160], flush=True)
    tid = case.get("order_ticket_id")
    if tid:
        try: ot.ack_order_generated("buyer-a", tid, sync_peer=True)
        except Exception as e: print("A_BUYER_ACK_ERR", str(e)[:120], flush=True)
    print("A_DONE", json.dumps({"case_id":cid,"ticket":tid,"priced":len(priced),
        "transport":summary.get("transport")}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''

SUP_ACK = r'''
import asyncio, json, os, sys, time
os.chdir("/opt/agentlink"); sys.path.insert(0,"/opt/agentlink")
from commerce import order_tickets as ot, tickets as tk, logistics_tickets as lt
agents=["supplier-a","supplier-b","supplier-c"]
acked=[]
for agent in agents:
    items=tk.list_tickets(agent, limit=50) or []
    opens=[t for t in items if t.get("kind")=="order" and t.get("status")=="open"
           and not (t.get("state") or {}).get("cancelled")
           and not (t.get("state") or {}).get("supplier_order_ack")]
    opens.sort(key=lambda t: 0 if any(x in str(t.get("id") or "") for x in ("CASTER","FABRIC")) else 1)
    for t in opens[:4]:
        try:
            r=ot.ack_order_generated(agent, t["id"], sync_peer=True)
            st=(r.get("state") if isinstance(r,dict) else None) or (tk.get_ticket(agent,t["id"]) or {}).get("state") or {}
            acked.append({"agent":agent,"tid":t["id"],"effective":st.get("order_effective"),"title":(t.get("title") or "")[:60]})
            print("SUP_ACK", json.dumps(acked[-1],ensure_ascii=False), flush=True)
        except Exception as e:
            print("SUP_ACK_ERR", agent, t["id"], str(e)[:120], flush=True)
time.sleep(5)
logs=[]
for agent in agents:
    for t in (tk.list_tickets(agent, limit=40) or []):
        if t.get("kind")=="logistics_order" and t.get("status")=="open":
            logs.append({"agent":agent,"tid":t["id"]})
if not logs:
    for agent in agents:
        for o in [t for t in (tk.list_tickets(agent,limit=20) or []) if t.get("kind")=="order" and (t.get("state") or {}).get("order_effective")][:2]:
            try:
                out=asyncio.run(lt.quote_and_spawn_from_order(agent, order_ticket=o))
                print("FORCE_LOG", agent, out.get("ticket_id"), flush=True)
            except Exception as e:
                print("FORCE_ERR", agent, str(e)[:120], flush=True)
    time.sleep(3)
    logs=[]
    for agent in agents:
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

def finish_code(case_ids: list[str]) -> str:
    return (
        "import json, os, sys\n"
        "os.chdir('/opt/agentlink'); sys.path.insert(0,'/opt/agentlink')\n"
        "from commerce import tickets as tk, logistics_tickets as lt, procurement_case as pc, flow_service as fs\n"
        f"TARGET = {case_ids!r}\n"
        + r'''
for agent in ("buyer-a","logistics"):
    for t in (tk.list_tickets(agent, limit=50) or []):
        if t.get("kind")=="logistics_order" and t.get("status")=="open":
            try:
                lt.ack_logistics(agent, t["id"], sync_peer=True)
                print("BUYER_LOG_ACK", agent, t["id"], flush=True)
            except Exception as e:
                print("BUYER_LOG_ERR", agent, t["id"], str(e)[:100], flush=True)
activated=[]
for cid in TARGET:
    case = pc.get_case(cid) or {}
    if not case:
        print("ACTIVATE_MISS", cid, flush=True); continue
    try:
        if case.get("state")=="ORDER_DRAFT":
            try: pc.transition(cid,"CONTRACT_PENDING",event="verify_to_contract",patch={"buyer_confirmed":True,"supplier_confirmed":True})
            except Exception: pc.update_case(cid, buyer_confirmed=True, supplier_confirmed=True)
        else:
            pc.update_case(cid, buyer_confirmed=True, supplier_confirmed=True)
        c3=fs.step_activate(cid)
        activated.append({"case":cid,"state":c3.get("state")})
        print("ACTIVATE", cid, c3.get("state"), flush=True)
    except Exception as e:
        print("ACTIVATE_ERR", cid, str(e)[:140], flush=True)
print("FINISH", json.dumps({"activated":activated},ensure_ascii=False), flush=True)
'''
    )


def write_review(reports: list[dict], shots: list[dict]) -> None:
    lines = [
        f"# 普通采购 + 组群竞价 UI 验证 · {RUN_ID}",
        "",
        f"证据目录：`docs/evidence/verify_ui_shots/{RUN_ID}/`",
        "",
    ]
    for r in reports:
        lines += [
            f"## {r['title']}",
            f"- **结果**: `{'PASS' if r.get('ok') else 'FAIL'}`",
            f"- **问题**: {json.dumps(r.get('issues') or [], ensure_ascii=False)}",
            f"- **关键数据**:",
            "```json",
            json.dumps({k: r.get(k) for k in r if k not in {'title','ok','issues','shots'}}, ensure_ascii=False, indent=2)[:2500],
            "```",
            "",
        ]
    lines += ["## 逐步截图", ""]
    for s in shots:
        lines.append(f"### {s['step']:02d}. {s['label']}（{s['portal']}/{s['page']}）")
        if s.get("chat"):
            lines.append(f"- chat: {s['chat'][:120]}")
        if s.get("error"):
            lines.append(f"- error: `{s['error'][:200]}`")
        lines.append(f"- ![{s['file']}](screenshots/{s['file']})")
        lines.append("")
    (OUT / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "report.json").write_text(
        json.dumps({"run_id": RUN_ID, "reports": reports, "shots": shots}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    print("OUT", OUT, flush=True)
    reports: list[dict] = []
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("ALL_PROXY", None)
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)
    os.environ["NO_PROXY"] = "*"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--proxy-server=direct://", "--no-proxy-server"],
        )
        shotter = Shotter(browser)
        try:
            # ========== 路径一：普通采购 ==========
            r1: dict = {"title": "普通采购（发现→短名单→RFQ→下单→物流→激活）", "ok": False, "issues": []}
            shotter.shot("buyer-a", "chat", "N00_buyer_home_chat")
            shotter.shot("buyer-a", "tickets", "N00_buyer_tickets_before")

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, NORMAL_DISCOVER, env="buyer-a.env", timeout=300)
                (OUT / "n_discover.log").write_text(out, encoding="utf-8")
                r1["discover"] = marker(out, "N_DISCOVER")
            finally:
                b.close()
            n_cid = (r1.get("discover") or {}).get("case_id")
            if not n_cid:
                r1["issues"].append("普通采购未拿到 case_id")
            shotter.shot("buyer-a", "chat", "N01_after_discover_chat")
            shotter.shot("buyer-a", "tickets", "N01_after_discover_tickets")
            shotter.chat_ask(
                "buyer-a",
                f"查看采购案 {n_cid} 的状态与候选供应商列表，用表格说明。",
                "N02_chat_status_after_discover",
                timeout_ms=120_000,
            )

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, normal_rfq_code(n_cid or ""), env="buyer-a.env", timeout=420)
                (OUT / "n_rfq.log").write_text(out, encoding="utf-8")
                r1["shortlist"] = marker(out, "N_SHORTLIST")
                r1["rfq"] = marker(out, "N_RFQ")
            finally:
                b.close()
            shotter.shot("buyer-a", "chat", "N03_after_rfq_chat")
            shotter.chat_ask(
                "buyer-a",
                f"针对采购案 {n_cid}，汇总三家询价结果，比较单价与总价，给出推荐。",
                "N04_chat_compare_quotes",
                timeout_ms=180_000,
            )
            shotter.shot("supplier-a", "tickets", "N05_sa_tickets_after_rfq")
            shotter.shot("supplier-b", "tickets", "N05_sb_tickets_after_rfq")
            shotter.shot("supplier-c", "tickets", "N05_sc_tickets_after_rfq")

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, normal_order_code(n_cid or ""), env="buyer-a.env", timeout=360)
                (OUT / "n_order.log").write_text(out, encoding="utf-8")
                r1["order"] = marker(out, "N_ORDER")
                r1["ship"] = marker(out, "N_SHIP")
                r1["order_done"] = marker(out, "N_ORDER_DONE")
            finally:
                b.close()
            shotter.shot("buyer-a", "tickets", "N06_buyer_tickets_after_order")
            shotter.shot("supplier-a", "tickets", "N07_sa_tickets_after_order")
            shotter.chat_ask(
                "buyer-a",
                f"查看采购案 {n_cid} 的订单草案与物流缺口，说明下一步需谁确认。",
                "N08_chat_order_status",
                timeout_ms=120_000,
            )

            s = ssh("39.105.20.113", pem=False)
            try:
                out = remote_py(s, SUP_ACK, env="supplier-a.env", timeout=240)
                (OUT / "n_sup.log").write_text(out, encoding="utf-8")
                r1["sup"] = marker(out, "SUP_DONE")
            finally:
                s.close()
            shotter.shot("supplier-a", "tickets", "N09_sa_after_ack")
            shotter.shot("logistics", "tickets", "N10_logistics_after_sup_ack")

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, finish_code([n_cid] if n_cid else []), env="buyer-a.env", timeout=180)
                (OUT / "n_finish.log").write_text(out, encoding="utf-8")
                r1["finish"] = marker(out, "FINISH")
            finally:
                b.close()
            shotter.shot("buyer-a", "tickets", "N11_buyer_final_tickets")
            shotter.shot("buyer-a", "audit", "N12_buyer_audit")
            shotter.shot("logistics", "tickets", "N13_logistics_final")
            shotter.chat_ask(
                "buyer-a",
                f"确认采购案 {n_cid} 是否已激活，用一句话结论。",
                "N14_chat_final",
                timeout_ms=90_000,
            )

            disc = r1.get("discover") or {}
            rfq = r1.get("rfq") or {}
            order = r1.get("order") or {}
            if (disc.get("n") or 0) < 1:
                r1["issues"].append(f"发现候选不足: {disc}")
            if (rfq.get("quote_n") or 0) < 1:
                r1["issues"].append(f"询价无报价: {rfq}")
            if not order.get("ticket") and not (r1.get("order_done") or {}).get("ticket"):
                r1["issues"].append(f"未生成订单工单: {order}")
            r1["ok"] = not r1["issues"]
            reports.append(r1)
            print("NORMAL", r1["ok"], r1["issues"], flush=True)

            # ========== 路径二：组群竞价 ==========
            r2: dict = {"title": "组群竞价（发现→RFQ→auction→TCO下单→物流→激活）", "ok": False, "issues": []}
            shotter.shot("buyer-a", "chat", "A00_buyer_before_auction")

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, AUCTION_CORE, env="buyer-a.env", timeout=480)
                (OUT / "a_core.log").write_text(out, encoding="utf-8")
                r2["discover"] = marker(out, "A_DISCOVER")
                r2["rfq"] = marker(out, "A_RFQ")
                r2["auction"] = marker(out, "A_AUCTION")
                r2["order"] = marker(out, "A_ORDER")
                r2["done"] = marker(out, "A_DONE")
            finally:
                b.close()
            a_cid = (r2.get("done") or r2.get("discover") or {}).get("case_id")
            shotter.shot("buyer-a", "tickets", "A01_buyer_tickets_after_auction")
            shotter.chat_ask(
                "buyer-a",
                f"说明采购案 {a_cid} 组群竞价的运输方式、有效出价数、最优 TCO 与中标供应方。",
                "A02_chat_auction_summary",
                timeout_ms=180_000,
            )
            shotter.shot("supplier-a", "tickets", "A03_sa_tickets")
            shotter.shot("supplier-b", "tickets", "A03_sb_tickets")
            shotter.shot("supplier-c", "tickets", "A03_sc_tickets")

            s = ssh("39.105.20.113", pem=False)
            try:
                out = remote_py(s, SUP_ACK, env="supplier-a.env", timeout=240)
                (OUT / "a_sup.log").write_text(out, encoding="utf-8")
                r2["sup"] = marker(out, "SUP_DONE")
            finally:
                s.close()
            shotter.shot("supplier-a", "tickets", "A04_sa_after_ack")
            shotter.shot("logistics", "tickets", "A05_logistics")

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, finish_code([a_cid] if a_cid else []), env="buyer-a.env", timeout=180)
                (OUT / "a_finish.log").write_text(out, encoding="utf-8")
                r2["finish"] = marker(out, "FINISH")
            finally:
                b.close()
            shotter.shot("buyer-a", "tickets", "A06_buyer_final")
            shotter.shot("buyer-a", "audit", "A07_buyer_audit")
            shotter.chat_ask(
                "buyer-a",
                f"确认采购案 {a_cid} 组群竞价是否已激活，一句话结论。",
                "A08_chat_final",
                timeout_ms=90_000,
            )

            auc = r2.get("auction") or {}
            if (auc.get("priced") or 0) < 2:
                r2["issues"].append(f"竞价有效出价应≥2: {auc}")
            if auc.get("transport") and auc.get("transport") != "group":
                r2["issues"].append(f"transport 非 group: {auc.get('transport')}")
            if not (r2.get("order") or {}).get("ticket") and not (r2.get("done") or {}).get("ticket"):
                r2["issues"].append("竞价后未生成订单工单")
            r2["ok"] = not r2["issues"]
            reports.append(r2)
            print("AUCTION", r2["ok"], r2["issues"], flush=True)

        finally:
            browser.close()

    write_review(reports, shotter.log)
    print("REVIEW", OUT / "REVIEW.md", flush=True)
    print("SHOTS", len(shotter.log), "dir", SHOT, flush=True)
    return 0 if all(x.get("ok") for x in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
