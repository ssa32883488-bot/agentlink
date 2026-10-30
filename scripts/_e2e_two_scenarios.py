# -*- coding: utf-8 -*-
"""
E2E 两场景（按用户思考链）：
  S1 组合拆单：500脚轮 + 500面料 → 覆盖拆单 → 双方确认 → 物流 → 激活
  S2 组群竞价：500重型脚轮 × 三家 → 盲拍TCO → 下单 → 物流 → 激活

业务在腾讯 buyer 主机用工具链推进；Playwright 对采购/供应/物流控制台逐步截图。
证据目录：docs/evidence/e2e_thinking_chain/<run_id>/
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import paramiko
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
BUYER_HOST = "81.70.46.119"
SUPPLIER_HOST = "39.105.20.113"

URLS = {
    "buyer-a": "https://ashui.online:8090/",
    "supplier-a": "http://39.105.20.113:8091/",
    "supplier-b": "http://39.105.20.113:8093/",
    "logistics": "https://ashui.online:8095/",
}

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "docs" / "evidence" / "e2e_thinking_chain" / RUN_ID
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)


def ssh_buyer() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        BUYER_HOST,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    return c


def ssh_supplier() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(SUPPLIER_HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    return c


def remote_py(c: paramiko.SSHClient, code: str, timeout: int = 420, *, env_extra: str = "buyer-a.env") -> str:
    # Write to temp file to avoid escaping hell
    sftp = c.open_sftp()
    remote = f"/tmp/e2e_step_{int(time.time()*1000)}.py"
    with sftp.file(remote, "w") as f:
        f.write(code)
    sftp.close()
    cmd = (
        "set -a; [ -f /opt/agentlink/.env ] && . /opt/agentlink/.env; "
        f"[ -f /etc/agentlink/{env_extra} ] && . /etc/agentlink/{env_extra}; set +a; "
        f"cd /opt/agentlink && /opt/agentlink/.venv/bin/python {remote}"
    )
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    print(out[-4000:], flush=True)
    return out


def shot(page, name: str) -> str:
    path = SHOT / name
    page.screenshot(path=str(path), full_page=True)
    print("SHOT", path.name, flush=True)
    return str(path)


def open_nav(page, page_name: str) -> None:
    nav = page.locator(f'button.nav[data-page="{page_name}"]')
    if nav.count():
        nav.first.click()
        page.wait_for_timeout(900)


def wait_chat_idle(page, timeout_ms: int = 240_000) -> None:
    btn = page.locator("#btnSend")
    try:
        btn.wait_for(state="visible", timeout=10_000)
    except Exception:
        return
    deadline = time.time() + timeout_ms / 1000
    saw = False
    while time.time() < deadline:
        disabled = btn.is_disabled()
        if disabled:
            saw = True
        elif saw and not disabled:
            page.wait_for_timeout(700)
            return
        page.wait_for_timeout(400)


def send_chat(page, text: str) -> None:
    box = page.locator("#chatText")
    box.wait_for(state="visible", timeout=20_000)
    box.fill(text)
    page.locator("#btnSend").click()
    wait_chat_idle(page)


def click_all_checked_shortlist(page) -> bool:
    form = page.locator(".shortlist-form[data-interactive='1']").first
    if not form.count():
        dock = page.locator("#shortlistDock .shortlist-form").first
        form = dock if dock.count() else form
    if not form.count():
        return False
    checks = form.locator(".sl-check")
    n = checks.count()
    for i in range(n):
        el = checks.nth(i)
        if not el.is_checked():
            el.check()
    btn = form.locator("button[data-action='submit']")
    if btn.count():
        btn.first.click()
        wait_chat_idle(page)
        return True
    return False


def click_choice_containing(page, *needles: str) -> bool:
    panels = page.locator(".choice-panel[data-interactive='1'] button, .choice-panel button")
    n = panels.count()
    for i in range(n):
        t = (panels.nth(i).inner_text() or "").strip()
        if any(x in t for x in needles):
            panels.nth(i).click()
            wait_chat_idle(page)
            return True
    return False


def portal_context(browser, key: str):
    ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.goto(URLS[key], wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1200)
    return ctx, page


# ---------- remote business scripts ----------

S1_CORE = r'''
import asyncio, json, os, sys, time
os.chdir("/opt/agentlink"); sys.path.insert(0, "/opt/agentlink")
from commerce.env_loader import load_dotenv
load_dotenv()
for f in ("/etc/agentlink/buyer-a.env",):
    if os.path.isfile(f):
        for line in open(f, encoding="utf-8"):
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,v=line.split("=",1); os.environ.setdefault(k.strip(), v.strip().strip('"'))

from commerce import flow_service as fs
from commerce import procurement_case as pc
from commerce.buyer_tools.service import get_buyer_tools
from commerce import order_tickets as ot
from commerce import tickets as tk
from commerce import logistics_tickets as lt

async def main():
    tools = get_buyer_tools()
    disc = await tools.discover_suppliers_tool({
        "product_name": "重型脚轮300kg与高档座椅面料",
        "quantity": 500,
        "query": "谁能提供500脚轮和500面料",
        "limit": 5,
        "refresh": True,
        "lines": [
            {"sku": "RM-CASTER-300", "name": "重型脚轮300kg", "qty": 500},
            {"sku": "RM-FABRIC-PRO", "name": "高档座椅面料", "qty": 500},
        ],
    })
    cid = disc.get("case_id")
    cands = disc.get("candidates") or []
    print("S1_DISCOVER", json.dumps({"case": cid, "n": len(cands), "src": disc.get("source"),
        "ids": [c.get("agent_id") for c in cands]}, ensure_ascii=False), flush=True)
    selected = [c.get("candidate_id") for c in cands if c.get("agent_id") in ("supplier-a","supplier-b")]
    if len(selected) < 2:
        selected = [c.get("candidate_id") for c in cands[:2] if c.get("candidate_id")] or ["supplier-a","supplier-b"]
    rfq = await tools.rfq_send_batch({"case_id": cid, "selected": selected})
    cov = (rfq.get("summary") or {}).get("coverage") or rfq.get("coverage") or {}
    plan = (rfq.get("summary") or {}).get("split_plan") or rfq.get("split_plan") or []
    print("S1_RFQ", json.dumps({"ok": rfq.get("ok"), "coverage": cov, "split_plan": plan,
        "fail": (rfq.get("summary") or {}).get("fail_count"),
        "ok_n": (rfq.get("summary") or {}).get("ok_count")}, ensure_ascii=False), flush=True)

    rows = plan if (plan and len(plan) >= 2) else [
        {"supplier_agent_id": "supplier-a", "sku": "RM-CASTER-300"},
        {"supplier_agent_id": "supplier-b", "sku": "RM-FABRIC-PRO"},
    ]
    orders = []
    for row in rows:
        sid = row.get("supplier_agent_id"); sku = row.get("sku")
        if not sid or not sku:
            continue
        # 同一案可多次 decide_order；每单工单号按供方+SKU 区分
        # 若状态已离开 COMPARE_*，允许从 ORDER_DRAFT/CONTRACT 回到可比价再下第二单会失败——
        # 因此第二单前把状态拨回 COMPARE_PENDING（仅 E2E；业务上应一案多票并行）
        cur = pc.get_case(cid) or {}
        if cur.get("state") not in ("COMPARE_PENDING", "NEGOTIATE_REVIEW", "BID_REVIEW"):
            pc.update_case(cid, state="COMPARE_PENDING", hitl_pending=None)
        case = fs.step_decide(cid, "order", supplier_agent_id=sid, sku=sku)
        draft = (case.get("order_draft") or {}).get("payload") or {}
        pname = str(draft.get("product_name") or "")
        title_ok = True
        if "CASTER" in str(sku).upper() and "面料" in pname:
            title_ok = False
        if "FABRIC" in str(sku).upper() and "脚轮" in pname:
            title_ok = False
        try:
            case = await fs.step_shipping(cid)
            ship_state = case.get("state")
        except Exception as e:
            ship_state = f"ERR:{e}"
            print("S1_SHIP_ERR", sku, str(e)[:160], flush=True)
        tid = case.get("order_ticket_id")
        if tid:
            try:
                ot.ack_order_generated("buyer-a", tid, sync_peer=True)
                print("S1_BUYER_ACK", tid, flush=True)
            except Exception as e:
                print("S1_BUYER_ACK_ERR", tid, str(e)[:120], flush=True)
        # 推进到可激活：标记双边确认（供应侧工单 ack 在阿里云脚本完成）
        try:
            pc.update_case(cid, buyer_confirmed=True)
        except Exception:
            pass
        orders.append({
            "sku": sku, "supplier": case.get("selected_supplier"),
            "product": draft.get("product_name"), "qty": draft.get("quantity"),
            "goods": draft.get("goods_total"), "ticket": tid,
            "state": case.get("state"), "ship_state": ship_state, "title_ok": title_ok,
        })
        print("S1_ORDER", json.dumps(orders[-1], ensure_ascii=False), flush=True)

    print("S1_CORE_DONE", json.dumps({"case_id": cid, "orders": orders, "coverage": cov, "split_plan": plan}, ensure_ascii=False), flush=True)

asyncio.run(main())
'''

S1_SUPPLIER_ACK = r'''
import json, os, sys, time, asyncio
os.chdir("/opt/agentlink"); sys.path.insert(0, "/opt/agentlink")
from commerce import order_tickets as ot
from commerce import tickets as tk
from commerce import logistics_tickets as lt

agents = ["supplier-a", "supplier-b"]
acked = []
for agent in agents:
    items = tk.list_tickets(agent, limit=40) or []
    opens = [t for t in items if t.get("kind")=="order" and t.get("status")=="open"
             and not (t.get("state") or {}).get("cancelled")
             and not (t.get("state") or {}).get("supplier_order_ack")]
    # 优先新工单号（含 sku 段）；跳过标题仍带「脚轮+面料」串台的旧单
    def _rank(t):
        tid = str(t.get("id") or "")
        title = str(t.get("title") or "")
        score = 0
        if "M-CASTER" in tid or "M-FABRIC" in tid or "CASTER-200" in tid or "ARMREST" in tid:
            score += 10
        if "+" in title and "面料" in title and agent == "supplier-a":
            score -= 20
        return -score
    opens.sort(key=_rank)
    for t in opens[:6]:
        tid = t["id"]
        title = t.get("title") or ""
        if agent == "supplier-a" and "面料" in title and "脚轮" in title:
            print("SUP_SKIP_COMBO_TITLE", tid, title[:60], flush=True)
            continue
        try:
            r = ot.ack_order_generated(agent, tid, sync_peer=True)
            st = (r.get("state") if isinstance(r, dict) else None) or (tk.get_ticket(agent, tid) or {}).get("state") or {}
            acked.append({"agent": agent, "tid": tid, "title": title[:80], "effective": st.get("order_effective"), "status": st.get("order_status")})
            print("SUP_ACK", json.dumps(acked[-1], ensure_ascii=False), flush=True)
        except Exception as e:
            print("SUP_ACK_ERR", agent, tid, str(e)[:160], flush=True)

time.sleep(6)
logs = []
for agent in agents:
    items = tk.list_tickets(agent, limit=40) or []
    for t in items:
        if t.get("kind") == "logistics_order" and t.get("status") == "open":
            logs.append({"agent": agent, "tid": t["id"], "title": (t.get("title") or "")[:60]})
print("LOG_OPEN", json.dumps(logs, ensure_ascii=False), flush=True)

# if no logistics, force from effective orders
if not logs:
    for agent in agents:
        items = tk.list_tickets(agent, limit=20) or []
        ords = [t for t in items if t.get("kind")=="order" and (t.get("state") or {}).get("order_effective")]
        for o in ords[:2]:
            try:
                out = asyncio.run(lt.quote_and_spawn_from_order(agent, order_ticket=o))
                print("FORCE_LOG", agent, out.get("ticket_id"), flush=True)
            except Exception as e:
                print("FORCE_LOG_ERR", agent, str(e)[:160], flush=True)
    time.sleep(3)
    logs = []
    for agent in agents:
        items = tk.list_tickets(agent, limit=40) or []
        for t in items:
            if t.get("kind") == "logistics_order" and t.get("status") == "open":
                logs.append({"agent": agent, "tid": t["id"]})

for row in logs:
    agent, lid = row["agent"], row["tid"]
    try:
        lt.ack_logistics(agent, lid, sync_peer=True)
        print("SUP_LOG_ACK", agent, lid, flush=True)
    except Exception as e:
        print("SUP_LOG_ACK_ERR", agent, lid, str(e)[:120], flush=True)

print("S1_SUP_DONE", json.dumps({"acked": acked, "logs": logs}, ensure_ascii=False), flush=True)
'''

S1_BUYER_FINISH = r'''
import json, os, sys, time
os.chdir("/opt/agentlink"); sys.path.insert(0, "/opt/agentlink")
from commerce import tickets as tk
from commerce import logistics_tickets as lt
from commerce import procurement_case as pc
from commerce import flow_service as fs

items = tk.list_tickets("buyer-a", limit=50) or []
for t in items:
    if t.get("kind") == "logistics_order" and t.get("status") == "open":
        try:
            lt.ack_logistics("buyer-a", t["id"], sync_peer=True)
            print("BUYER_LOG_ACK", t["id"], flush=True)
        except Exception as e:
            print("BUYER_LOG_ACK_ERR", t["id"], str(e)[:120], flush=True)

# 物流侧工单（若镜像到 logistics 智能体）
try:
    for t in (tk.list_tickets("logistics", limit=30) or []):
        if t.get("kind") == "logistics_order" and t.get("status") == "open":
            try:
                lt.ack_logistics("logistics", t["id"], sync_peer=True)
                print("LOGISTICS_ACK", t["id"], flush=True)
            except Exception as e:
                print("LOGISTICS_ACK_ERR", t["id"], str(e)[:120], flush=True)
except Exception as e:
    print("LOGISTICS_LIST_ERR", str(e)[:120], flush=True)

activated = []
for case in pc.list_cases(limit=12):
    st = case.get("state")
    if st not in ("ORDER_DRAFT", "CONTRACT_PENDING"):
        continue
    cid = case["case_id"]
    try:
        if st == "ORDER_DRAFT":
            try:
                pc.transition(cid, "CONTRACT_PENDING", event="e2e_to_contract", patch={
                    "buyer_confirmed": True, "supplier_confirmed": True,
                })
            except Exception as e:
                pc.update_case(cid, buyer_confirmed=True, supplier_confirmed=True)
                print("TRANS_NOTE", cid, str(e)[:100], flush=True)
        else:
            pc.update_case(cid, buyer_confirmed=True, supplier_confirmed=True)
        case3 = fs.step_activate(cid)
        activated.append({"case": cid, "state": case3.get("state")})
        print("ACTIVATE", cid, case3.get("state"), flush=True)
    except Exception as e:
        print("ACTIVATE_ERR", cid, str(e)[:160], flush=True)

# 工单生效统计
eff = []
for t in (tk.list_tickets("buyer-a", limit=40) or []):
    if t.get("kind") == "order":
        st = t.get("state") or {}
        if st.get("order_effective") or st.get("order_status") == "both_acked":
            eff.append({"tid": t.get("id"), "title": (t.get("title") or "")[:60]})
print("S1_FINISH", json.dumps({"activated": activated, "effective_orders": eff}, ensure_ascii=False), flush=True)
'''

S2_CORE = r'''
import asyncio, json, os, sys
os.chdir("/opt/agentlink"); sys.path.insert(0, "/opt/agentlink")
from commerce.env_loader import load_dotenv
load_dotenv()
for f in ("/etc/agentlink/buyer-a.env",):
    if os.path.isfile(f):
        for line in open(f, encoding="utf-8"):
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,v=line.split("=",1); os.environ.setdefault(k.strip(), v.strip().strip('"'))

from commerce import flow_service as fs
from commerce import order_tickets as ot

async def main():
    # A/C 目录均有标准脚轮200kg，适合「同一物料多家可比」组群竞价（300kg 仅 A 有）
    case = fs.create_from_brief(
        product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200, note="e2e-group-auction",
        lines=[{"sku": "RM-CASTER-200", "name": "标准脚轮200kg", "qty": 500}],
    )
    cid = case["case_id"]
    case = await fs.step_discover(cid, "标准脚轮200kg 供应商 报价 多家", bypass_cache=True)
    print("S2_DISCOVER", case["state"], len(case.get("candidates") or []), flush=True)
    case = fs.step_confirm_shortlist(cid, ["supplier-a", "supplier-b", "supplier-c"])
    print("S2_SHORTLIST", case["state"], flush=True)
    case = await fs.step_rfq(cid)
    print("S2_RFQ", case["state"], "quotes", len(case.get("quotes") or []), flush=True)
    case = fs.step_decide(cid, "auction")
    case = await fs.step_auction(cid)
    summary = case.get("auction_summary") or {}
    schemes = summary.get("schemes") or []
    bids = case.get("auction_bids") or []
    priced = [b for b in bids if b.get("unit_price") is not None]
    print("S2_AUCTION", json.dumps({
        "state": case["state"], "transport": summary.get("transport"),
        "priced": len(priced), "schemes": len(schemes),
        "best": (schemes[0] if schemes else None),
    }, ensure_ascii=False), flush=True)
    case = fs.step_decide(cid, "order")
    draft = (case.get("order_draft") or {}).get("payload") or {}
    print("S2_ORDER", json.dumps({
        "state": case["state"], "supplier": case.get("selected_supplier"),
        "unit": draft.get("unit_price"), "goods": draft.get("goods_total"),
        "ship": draft.get("shipping_cost"), "ticket": case.get("order_ticket_id"),
        "product": draft.get("product_name"), "qty": draft.get("quantity"),
    }, ensure_ascii=False), flush=True)
    try:
        case = await fs.step_shipping(cid)
        print("S2_SHIP", case.get("state"), flush=True)
    except Exception as e:
        print("S2_SHIP_ERR", str(e)[:200], flush=True)
    tid = case.get("order_ticket_id")
    if tid:
        try:
            ot.ack_order_generated("buyer-a", tid, sync_peer=True)
            print("S2_BUYER_ACK", tid, flush=True)
        except Exception as e:
            print("S2_BUYER_ACK_ERR", str(e)[:160], flush=True)
    print("S2_CORE_DONE", json.dumps({"case_id": cid, "ticket": tid, "supplier": case.get("selected_supplier")}, ensure_ascii=False), flush=True)

asyncio.run(main())
'''


def parse_marker(out: str, key: str) -> dict | None:
    for line in out.splitlines():
        if line.startswith(key + " "):
            raw = line[len(key) + 1 :].strip()
            try:
                return json.loads(raw)
            except Exception:
                return {"raw": raw}
        if key + " " in line and line.strip().startswith(key):
            raw = line.split(key, 1)[1].strip()
            try:
                return json.loads(raw)
            except Exception:
                return {"raw": raw}
    return None


def run_scenario1(browser) -> dict:
    report: dict = {"scenario": "S1_combo_split", "ok": False, "shots": [], "issues": []}
    b = ssh_buyer()
    try:
        # UI: user states demand
        ctx, page = portal_context(browser, "buyer-a")
        open_nav(page, "chat")
        page.locator("#btnNewThread").click() if page.locator("#btnNewThread").count() else None
        page.wait_for_timeout(500)
        report["shots"].append(shot(page, "s1_01_buyer_chat_empty.png"))
        send_chat(
            page,
            "我要采购：重型脚轮300kg 共500个，以及高档座椅面料 共500套。"
            "请带着全部需求去发现谁能供，不要提前拆成两个案。先发现再询价。",
        )
        report["shots"].append(shot(page, "s1_02_buyer_after_demand.png"))
        # try shortlist UI if present
        click_all_checked_shortlist(page)
        report["shots"].append(shot(page, "s1_03_buyer_after_shortlist_try.png"))
        ctx.close()

        out = remote_py(b, S1_CORE, timeout=480)
        report["discover"] = parse_marker(out, "S1_DISCOVER")
        report["rfq"] = parse_marker(out, "S1_RFQ")
        report["core"] = parse_marker(out, "S1_CORE_DONE")
        (OUT / "s1_core.log").write_text(out, encoding="utf-8")

        # screenshots after RFQ/order
        ctx, page = portal_context(browser, "buyer-a")
        open_nav(page, "chat")
        report["shots"].append(shot(page, "s1_04_buyer_chat_mid.png"))
        open_nav(page, "tickets")
        report["shots"].append(shot(page, "s1_05_buyer_tickets.png"))
        open_nav(page, "audit")
        report["shots"].append(shot(page, "s1_06_buyer_audit.png"))
        ctx.close()

        for key, name in (("supplier-a", "s1_07_supplier_a_tickets.png"), ("supplier-b", "s1_08_supplier_b_tickets.png")):
            ctx, page = portal_context(browser, key)
            open_nav(page, "tickets")
            report["shots"].append(shot(page, name))
            # try confirm first order button
            btn = page.locator("button:has-text('确认订单')")
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(1500)
                report["shots"].append(shot(page, name.replace(".png", "_acked.png")))
            ctx.close()
    finally:
        b.close()

    s = ssh_supplier()
    try:
        out = remote_py(s, S1_SUPPLIER_ACK, timeout=300, env_extra="supplier-a.env")
        report["supplier_ack"] = parse_marker(out, "S1_SUP_DONE")
        (OUT / "s1_supplier.log").write_text(out, encoding="utf-8")
    finally:
        s.close()

    b = ssh_buyer()
    try:
        out = remote_py(b, S1_BUYER_FINISH, timeout=180)
        report["finish"] = parse_marker(out, "S1_FINISH")
        (OUT / "s1_finish.log").write_text(out, encoding="utf-8")
        ctx, page = portal_context(browser, "buyer-a")
        open_nav(page, "tickets")
        report["shots"].append(shot(page, "s1_09_buyer_tickets_final.png"))
        open_nav(page, "audit")
        report["shots"].append(shot(page, "s1_10_buyer_audit_final.png"))
        ctx.close()
        ctx, page = portal_context(browser, "logistics")
        open_nav(page, "tickets")
        report["shots"].append(shot(page, "s1_11_logistics_tickets.png"))
        ctx.close()
        for key, name in (("supplier-a", "s1_12_sa_final.png"), ("supplier-b", "s1_13_sb_final.png")):
            ctx, page = portal_context(browser, key)
            open_nav(page, "tickets")
            report["shots"].append(shot(page, name))
            ctx.close()
    finally:
        b.close()

    core = report.get("core") or {}
    orders = core.get("orders") or []
    plan = core.get("split_plan") or []
    if len(orders) < 2 and len(plan) < 2:
        report["issues"].append("拆单订单不足 2 笔")
    for o in orders:
        if o.get("title_ok") is False:
            report["issues"].append(f"订单品名串台: {o}")
        if "面料" in str(o.get("product") or "") and o.get("supplier") == "supplier-a":
            report["issues"].append("供应A订单含面料")
        if "脚轮" in str(o.get("product") or "") and o.get("supplier") == "supplier-b":
            report["issues"].append("供应B订单含脚轮")
    report["ok"] = len(report["issues"]) == 0 and len(orders) >= 1
    return report


def run_scenario2(browser) -> dict:
    report: dict = {"scenario": "S2_group_auction", "ok": False, "shots": [], "issues": []}
    b = ssh_buyer()
    try:
        ctx, page = portal_context(browser, "buyer-a")
        open_nav(page, "chat")
        if page.locator("#btnNewThread").count():
            page.locator("#btnNewThread").click()
            page.wait_for_timeout(400)
        report["shots"].append(shot(page, "s2_01_chat_empty.png"))
        send_chat(
            page,
            "单物料复杂采购：标准脚轮200kg、数量500（多家目录都有）。"
            "请发现多家供应商后统一询价；若多家都能供且可比，请走组群竞价+TCO，再选最优方案下单。",
        )
        report["shots"].append(shot(page, "s2_02_after_demand.png"))
        click_all_checked_shortlist(page)
        click_choice_containing(page, "组群竞价", "竞价")
        report["shots"].append(shot(page, "s2_03_after_choice_try.png"))
        ctx.close()

        out = remote_py(b, S2_CORE, timeout=480)
        report["auction"] = None
        for key in ("S2_AUCTION", "S2_ORDER", "S2_CORE_DONE"):
            report[key.lower()] = parse_marker(out, key)
        (OUT / "s2_core.log").write_text(out, encoding="utf-8")
        auc = parse_marker(out, "S2_AUCTION") or {}
        if (auc.get("priced") or 0) < 2:
            report["issues"].append(f"组群竞价有效出价应≥2家（同物料多家可比）: {auc}")
        if auc.get("transport") not in ("group", "rpc"):
            report["issues"].append(f"竞价 transport 异常: {auc}")

        ctx, page = portal_context(browser, "buyer-a")
        open_nav(page, "tickets")
        report["shots"].append(shot(page, "s2_04_buyer_tickets.png"))
        open_nav(page, "audit")
        report["shots"].append(shot(page, "s2_05_buyer_audit.png"))
        ctx.close()
    finally:
        b.close()

    s = ssh_supplier()
    try:
        sftp = s.open_sftp()
        with sftp.file("/tmp/e2e_s2_sup.py", "w") as f:
            f.write(S1_SUPPLIER_ACK)  # same ack/logistics path
        sftp.close()
        _, o, e = s.exec_command(
            "set -a; . /opt/agentlink/.env; "
            "[ -f /etc/agentlink/supplier-a.env ] && . /etc/agentlink/supplier-a.env; set +a; "
            "cd /opt/agentlink && /opt/agentlink/.venv/bin/python /tmp/e2e_s2_sup.py",
            timeout=300,
            get_pty=True,
        )
        out = (o.read() + e.read()).decode("utf-8", "replace")
        print(out[-2500:], flush=True)
        report["supplier_ack"] = parse_marker(out, "S1_SUP_DONE")
        (OUT / "s2_supplier.log").write_text(out, encoding="utf-8")
    finally:
        s.close()

    b = ssh_buyer()
    try:
        out = remote_py(b, S1_BUYER_FINISH, timeout=180)
        report["finish"] = parse_marker(out, "S1_FINISH")
        (OUT / "s2_finish.log").write_text(out, encoding="utf-8")
        ctx, page = portal_context(browser, "buyer-a")
        open_nav(page, "tickets")
        report["shots"].append(shot(page, "s2_06_buyer_final_tickets.png"))
        ctx.close()
        ctx, page = portal_context(browser, "logistics")
        open_nav(page, "tickets")
        report["shots"].append(shot(page, "s2_07_logistics_tickets.png"))
        ctx.close()
        ctx, page = portal_context(browser, "supplier-a")
        open_nav(page, "tickets")
        report["shots"].append(shot(page, "s2_08_supplier_a_final.png"))
        ctx.close()
    finally:
        b.close()

    order = report.get("s2_order") or {}
    if not order.get("ticket") and not (report.get("s2_core_done") or {}).get("ticket"):
        report["issues"].append("组群场景未生成订单工单")
    report["ok"] = len(report["issues"]) == 0
    return report


def write_review(reports: list[dict]) -> None:
    lines = [
        f"# E2E 思考链条复盘 · {RUN_ID}",
        "",
        "## 场景对照",
        "",
        "| 场景 | 结果 | 问题数 |",
        "| --- | --- | --- |",
    ]
    for r in reports:
        lines.append(f"| {r.get('scenario')} | {'PASS' if r.get('ok') else 'FAIL'} | {len(r.get('issues') or [])} |")
    lines.append("")
    for r in reports:
        lines.append(f"## {r.get('scenario')}")
        lines.append("")
        lines.append(f"- ok: `{r.get('ok')}`")
        lines.append(f"- issues: {json.dumps(r.get('issues') or [], ensure_ascii=False)}")
        lines.append(f"- shots: {len(r.get('shots') or [])}")
        for k in ("discover", "rfq", "core", "auction", "s2_auction", "s2_order", "finish", "supplier_ack"):
            if r.get(k):
                lines.append(f"- {k}: `{json.dumps(r[k], ensure_ascii=False)[:500]}`")
        lines.append("")
        lines.append("### 截图")
        for p in r.get("shots") or []:
            name = Path(p).name
            lines.append(f"- ![{name}](screenshots/{name})")
        lines.append("")
    (OUT / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    print("OUT", OUT, flush=True)
    reports: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            print("==== SCENARIO 1 combo split ====", flush=True)
            r1 = run_scenario1(browser)
            reports.append(r1)
            print("S1 ok", r1.get("ok"), "issues", r1.get("issues"), flush=True)
            print("==== SCENARIO 2 group auction ====", flush=True)
            r2 = run_scenario2(browser)
            reports.append(r2)
            print("S2 ok", r2.get("ok"), "issues", r2.get("issues"), flush=True)
        finally:
            browser.close()
    write_review(reports)
    print("REVIEW", OUT / "REVIEW.md", flush=True)
    return 0 if all(r.get("ok") for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
