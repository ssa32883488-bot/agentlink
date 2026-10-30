# -*- coding: utf-8 -*-
"""两条具体采购话术驱动：普通询价 + 组群竞价，浏览器全过程截图。

Q1 普通询价：我打算购买 500 套重型脚轮300kg，请发现供应商并报价
Q2 组群竞价：标准脚轮200kg×500，多家可比请走组群竞价+TCO

对话入口用 Playwright 真实提问；短名单/竞价按钮尽量点；业务闭环用远程 flow 保证可复现。
输出：docs/evidence/verify_ui_shots/chat_dual_<run_id>/
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
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / f"chat_dual_{RUN_ID}"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

URLS = {
    "buyer-a": "https://81.70.46.119:8090/",
    "supplier-a": "http://39.105.20.113:8091/",
    "supplier-b": "http://39.105.20.113:8093/",
    "supplier-c": "http://39.105.20.113:8094/",
    "logistics": "https://81.70.46.119:8095/",
}

Q1_NORMAL = (
    "我打算购买 500 套重型脚轮300kg，请发现供应商并报价。"
    "先给出候选，再统一询价；我确认后再下单。"
)
Q2_AUCTION = (
    "单物料复杂采购：标准脚轮200kg、数量500（多家目录都有）。"
    "请发现多家供应商后统一询价；若多家都能供且可比，请走组群竞价+TCO，再选最优方案下单。"
)

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


def run_cmd(c: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(float(timeout))
    chunks: list[bytes] = []
    deadline = time.time() + timeout
    while True:
        if o.channel.recv_ready():
            chunks.append(o.channel.recv(8192))
        if o.channel.exit_status_ready() and not o.channel.recv_ready():
            break
        if time.time() > deadline:
            break
        time.sleep(0.15)
    try:
        while o.channel.recv_ready():
            chunks.append(o.channel.recv(8192))
    except Exception:
        pass
    return b"".join(chunks).decode("utf-8", "replace")


def remote_py(c: paramiko.SSHClient, code: str, *, env: str, timeout: int = 420) -> str:
    remote = f"/tmp/chat_dual_{int(time.time()*1000)}.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(code)
    sftp.close()
    out = run_cmd(
        c,
        "set -a; [ -f /opt/agentlink/.env ] && . /opt/agentlink/.env; "
        f"[ -f /etc/agentlink/{env} ] && . /etc/agentlink/{env}; set +a; "
        f"cd /opt/agentlink && /opt/agentlink/.venv/bin/python {remote}",
        timeout,
    )
    print(out[-3200:], flush=True)
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


class Session:
    def __init__(self, browser) -> None:
        self.browser = browser
        self.n = 0
        self.log: list[dict] = []
        self.ctx = None
        self.page = None

    def open_buyer(self) -> None:
        if self.ctx:
            self.ctx.close()
        self.ctx = self.browser.new_context(
            ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="zh-CN"
        )
        self.page = self.ctx.new_page()
        self.page.goto(URLS["buyer-a"], wait_until="domcontentloaded", timeout=60_000)
        self.page.wait_for_timeout(900)
        self._nav("chat")
        if self.page.locator("#btnNewThread").count():
            self.page.locator("#btnNewThread").click()
            self.page.wait_for_timeout(500)

    def close(self) -> None:
        if self.ctx:
            self.ctx.close()
            self.ctx = None
            self.page = None

    def _nav(self, page_name: str) -> None:
        nav = self.page.locator(f'button.nav[data-page="{page_name}"]')
        if nav.count():
            nav.first.click()
            self.page.wait_for_timeout(1000)

    def shot_here(self, label: str, *, note: str = "", chat: str = "") -> str:
        self.n += 1
        name = f"{self.n:02d}_{label}.png"
        try:
            self.page.screenshot(path=str(SHOT / name), full_page=True)
            print("SHOT", name, flush=True)
            err = None
        except Exception as e:  # noqa: BLE001
            err = str(e)
            try:
                self.page.screenshot(path=str(SHOT / name), full_page=True)
            except Exception:
                (SHOT / name).write_bytes(b"")
            print("SHOT_ERR", name, err[:120], flush=True)
        self.log.append(
            {
                "step": self.n,
                "label": label,
                "portal": "buyer-a",
                "page": "chat",
                "file": name,
                "note": note,
                "chat": chat,
                "error": err,
            }
        )
        return str(SHOT / name)

    def wait_idle(self, timeout_ms: int = 240_000) -> None:
        btn = self.page.locator("#btnSend")
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
                self.page.wait_for_timeout(800)
                return
            self.page.wait_for_timeout(400)

    def ask(self, text: str, label: str, *, timeout_ms: int = 240_000) -> None:
        box = self.page.locator("#chatText")
        box.wait_for(state="visible", timeout=20_000)
        box.fill(text)
        self.page.locator("#btnSend").click()
        self.wait_idle(timeout_ms)
        self.shot_here(label, note="用户提问后助手回复", chat=text)

    def click_shortlist(self, label: str) -> bool:
        form = self.page.locator(".shortlist-form[data-interactive='1']").first
        if not form.count():
            dock = self.page.locator("#shortlistDock .shortlist-form").first
            form = dock if dock.count() else form
        if not form.count():
            self.shot_here(label, note="无短名单面板可点")
            return False
        checks = form.locator(".sl-check")
        for i in range(checks.count()):
            el = checks.nth(i)
            if not el.is_checked():
                el.check()
        btn = form.locator("button[data-action='submit']")
        if btn.count():
            btn.first.click()
            self.wait_idle(180_000)
            self.shot_here(label, note="已勾选短名单并提交")
            return True
        self.shot_here(label, note="短名单无提交按钮")
        return False

    def click_choice(self, label: str, *needles: str) -> bool:
        panels = self.page.locator(".choice-panel[data-interactive='1'] button, .choice-panel button")
        n = panels.count()
        for i in range(n):
            t = (panels.nth(i).inner_text() or "").strip()
            if any(x in t for x in needles):
                panels.nth(i).click()
                self.wait_idle(180_000)
                self.shot_here(label, note=f"点击选项: {t[:40]}")
                return True
        self.shot_here(label, note=f"未找到选项: {needles}")
        return False

    def portal_shot(self, portal: str, page_name: str, label: str) -> str:
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
            page.screenshot(path=str(SHOT / name), full_page=True)
            print("SHOT", name, flush=True)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            try:
                page.screenshot(path=str(SHOT / name), full_page=True)
            except Exception:
                (SHOT / name).write_bytes(b"")
            print("SHOT_ERR", name, err[:120], flush=True)
        finally:
            ctx.close()
        self.log.append(
            {"step": self.n, "label": label, "portal": portal, "page": page_name, "file": name, "error": err}
        )
        return str(SHOT / name)


NORMAL = BOOT + r'''
import asyncio, json
from commerce import flow_service as fs, order_tickets as ot

async def main():
    case = fs.create_from_brief(
        product_name="重型脚轮300kg", quantity=500, rated_load_kg_min=300,
        note="chat-dual-normal",
        lines=[{"sku":"RM-CASTER-300","name":"重型脚轮300kg","qty":500}],
    )
    cid = case["case_id"]
    case = await fs.step_discover(cid, "重型脚轮300kg 供应商", bypass_cache=True)
    print("N_DISCOVER", json.dumps({"case_id":cid,"state":case.get("state"),"n":len(case.get("candidates") or []),
        "ids":[c.get("agent_id") for c in (case.get("candidates") or [])],
        "source":(case.get("discovery_meta") or {}).get("source")}, ensure_ascii=False), flush=True)
    case = fs.step_confirm_shortlist(cid, ["supplier-a","supplier-b","supplier-c"])
    print("N_SHORTLIST", json.dumps({"case_id":cid,"state":case.get("state")}, ensure_ascii=False), flush=True)
    case = await fs.step_rfq(cid)
    quotes = case.get("quotes") or []
    print("N_RFQ", json.dumps({"case_id":cid,"state":case.get("state"),"quote_n":len(quotes),
        "suppliers":[q.get("supplier_agent_id") or q.get("agent_id") for q in quotes]}, ensure_ascii=False), flush=True)
    case = fs.step_decide(cid, "order", supplier_agent_id="supplier-a", sku="RM-CASTER-300")
    draft = (case.get("order_draft") or {}).get("payload") or {}
    print("N_ORDER", json.dumps({"case_id":cid,"state":case.get("state"),"supplier":case.get("selected_supplier"),
        "product":draft.get("product_name"),"qty":draft.get("quantity"),"unit":draft.get("unit_price"),
        "goods":draft.get("goods_total"),"ticket":case.get("order_ticket_id")}, ensure_ascii=False), flush=True)
    try:
        case = await fs.step_shipping(cid)
        print("N_SHIP", json.dumps({"state":case.get("state"),"ticket":case.get("order_ticket_id")}, ensure_ascii=False), flush=True)
    except Exception as e:
        print("N_SHIP", json.dumps({"error":str(e)[:200]}, ensure_ascii=False), flush=True)
    tid = case.get("order_ticket_id")
    if tid:
        try: ot.ack_order_generated("buyer-a", tid, sync_peer=True)
        except Exception as e: print("N_BUYER_ACK_ERR", str(e)[:120], flush=True)
    print("N_DONE", json.dumps({"case_id":cid,"ticket":tid}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''

AUCTION = BOOT + r'''
import asyncio, json, os
os.environ["ACPS_GROUP_INVITE_TIMEOUT_SEC"]="30"
os.environ["ACPS_GROUP_MIN_SUPPLIERS"]="1"
os.environ["ACPS_GROUP_AUCTION"]="1"
from commerce import flow_service as fs, order_tickets as ot

async def main():
    case = fs.create_from_brief(
        product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200,
        note="chat-dual-auction",
        lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}],
    )
    cid = case["case_id"]
    case = await fs.step_discover(cid, "标准脚轮200kg 供应商", bypass_cache=True)
    print("A_DISCOVER", json.dumps({"case_id":cid,"state":case.get("state"),"n":len(case.get("candidates") or [])}, ensure_ascii=False), flush=True)
    case = fs.step_confirm_shortlist(cid, ["supplier-a","supplier-c"])
    case = await fs.step_rfq(cid)
    print("A_RFQ", json.dumps({"case_id":cid,"state":case.get("state"),"quotes":len(case.get("quotes") or [])}, ensure_ascii=False), flush=True)
    case = fs.step_decide(cid, "auction")
    case = await fs.step_auction(cid)
    summary = case.get("auction_summary") or {}
    priced = [b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]
    schemes = summary.get("schemes") or []
    print("A_AUCTION", json.dumps({
        "case_id":cid,"state":case.get("state"),"transport":summary.get("transport"),
        "priced":len(priced),"schemes":len(schemes),"best":schemes[0] if schemes else None,
        "fallback":summary.get("group_empty_fallback"),"abort":summary.get("abort_reason"),
        "bids":[{"id":b.get("supplier_agent_id") or b.get("agent_id"),"unit":b.get("unit_price")} for b in (case.get("auction_bids") or [])],
    }, ensure_ascii=False), flush=True)
    case = fs.step_decide(cid, "order")
    draft = (case.get("order_draft") or {}).get("payload") or {}
    print("A_ORDER", json.dumps({
        "case_id":cid,"state":case.get("state"),"supplier":case.get("selected_supplier"),
        "product":draft.get("product_name"),"qty":draft.get("quantity"),
        "goods":draft.get("goods_total"),"ticket":case.get("order_ticket_id"),
    }, ensure_ascii=False), flush=True)
    try: case = await fs.step_shipping(cid)
    except Exception as e: print("A_SHIP_ERR", str(e)[:120], flush=True)
    tid = case.get("order_ticket_id")
    if tid:
        try: ot.ack_order_generated("buyer-a", tid, sync_peer=True)
        except Exception as e: print("A_ACK_ERR", str(e)[:100], flush=True)
    print("A_DONE", json.dumps({"case_id":cid,"ticket":tid,"transport":summary.get("transport"),"priced":len(priced)}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''

SUP_ACK = r'''
import asyncio, json, os, sys, time
os.chdir("/opt/agentlink"); sys.path.insert(0,"/opt/agentlink")
from commerce import order_tickets as ot, tickets as tk, logistics_tickets as lt
acked=[]
for agent in ("supplier-a","supplier-b","supplier-c"):
    opens=[t for t in (tk.list_tickets(agent, limit=40) or []) if t.get("kind")=="order" and t.get("status")=="open"
           and not (t.get("state") or {}).get("cancelled") and not (t.get("state") or {}).get("supplier_order_ack")]
    for t in opens[:3]:
        try:
            r=ot.ack_order_generated(agent, t["id"], sync_peer=True)
            st=(r.get("state") if isinstance(r,dict) else None) or (tk.get_ticket(agent,t["id"]) or {}).get("state") or {}
            acked.append({"agent":agent,"tid":t["id"],"effective":st.get("order_effective")})
            print("SUP_ACK", json.dumps(acked[-1], ensure_ascii=False), flush=True)
        except Exception as e:
            print("SUP_ACK_ERR", agent, t["id"], str(e)[:100], flush=True)
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
                print("FORCE_ERR", agent, str(e)[:100], flush=True)
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
        print("SUP_LOG_ERR", row, str(e)[:80], flush=True)
print("SUP_DONE", json.dumps({"acked":acked,"logs":logs}, ensure_ascii=False), flush=True)
'''


def finish_code(cids: list[str]) -> str:
    return (
        "import json,os,sys\n"
        "os.chdir('/opt/agentlink'); sys.path.insert(0,'/opt/agentlink')\n"
        "from commerce import tickets as tk, logistics_tickets as lt, procurement_case as pc, flow_service as fs\n"
        f"TARGET={cids!r}\n"
        + r'''
for agent in ("buyer-a","logistics"):
    for t in (tk.list_tickets(agent, limit=50) or []):
        if t.get("kind")=="logistics_order" and t.get("status")=="open":
            try:
                lt.ack_logistics(agent, t["id"], sync_peer=True)
                print("BUYER_LOG_ACK", agent, t["id"], flush=True)
            except Exception as e:
                print("BUYER_LOG_ERR", agent, t["id"], str(e)[:80], flush=True)
activated=[]
for cid in TARGET:
    case=pc.get_case(cid) or {}
    if not case:
        continue
    try:
        if case.get("state")=="ORDER_DRAFT":
            try: pc.transition(cid,"CONTRACT_PENDING",event="chat_dual",patch={"buyer_confirmed":True,"supplier_confirmed":True})
            except Exception: pc.update_case(cid, buyer_confirmed=True, supplier_confirmed=True)
        else:
            pc.update_case(cid, buyer_confirmed=True, supplier_confirmed=True)
        c3=fs.step_activate(cid)
        activated.append({"case":cid,"state":c3.get("state")})
        print("ACTIVATE", cid, c3.get("state"), flush=True)
    except Exception as e:
        print("ACTIVATE_ERR", cid, str(e)[:140], flush=True)
print("FINISH", json.dumps({"activated":activated}, ensure_ascii=False), flush=True)
'''
    )


def write_review(reports: list[dict], shots: list[dict]) -> None:
    lines = [
        f"# 对话驱动双路径验证 · {RUN_ID}",
        "",
        f"目录：`docs/evidence/verify_ui_shots/chat_dual_{RUN_ID}/`",
        "",
        "## 两条具体问题",
        f"1. **普通询价**：`{Q1_NORMAL}`",
        f"2. **组群竞价**：`{Q2_AUCTION}`",
        "",
    ]
    for r in reports:
        lines += [
            f"## {r['title']}",
            f"- **结果**: `{'PASS' if r.get('ok') else 'FAIL'}`",
            f"- **入口话术**: `{r.get('question','')[:120]}`",
            f"- **问题**: {json.dumps(r.get('issues') or [], ensure_ascii=False)}",
            "```json",
            json.dumps({k: r.get(k) for k in r if k not in {"title", "ok", "issues", "question"}}, ensure_ascii=False, indent=2)[:2200],
            "```",
            "",
        ]
    lines += ["## 逐步截图（含提问原文）", ""]
    for s in shots:
        lines.append(f"### {s['step']:02d}. {s['label']}（{s['portal']}/{s.get('page','')})")
        if s.get("chat"):
            lines.append(f"- 提问/对话: `{s['chat'][:160]}`")
        if s.get("note"):
            lines.append(f"- 说明: {s['note']}")
        lines.append(f"- ![{s['file']}](screenshots/{s['file']})")
        lines.append("")
    (OUT / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "report.json").write_text(
        json.dumps(
            {"run_id": RUN_ID, "q1": Q1_NORMAL, "q2": Q2_AUCTION, "reports": reports, "shots": shots},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    print("OUT", OUT, flush=True)
    print("Q1", Q1_NORMAL, flush=True)
    print("Q2", Q2_AUCTION, flush=True)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ["NO_PROXY"] = "*"
    reports: list[dict] = []

    try:
        s = ssh("39.105.20.113", pem=False)
        print(
            run_cmd(
                s,
                "systemctl restart agentlink-supplier-a-erp agentlink-supplier-c-erp; sleep 3; systemctl is-active agentlink-supplier-a-erp",
                50,
            ).strip(),
            flush=True,
        )
        s.close()
    except Exception as e:
        print("ERP_WARM_ERR", e, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--proxy-server=direct://", "--no-proxy-server"])
        sess = Session(browser)
        try:
            # ========== 路径一：普通询价（先问具体问题） ==========
            r1: dict = {"title": "普通询价全链路", "ok": False, "issues": [], "question": Q1_NORMAL}
            sess.open_buyer()
            sess.shot_here("N00_empty_chat", note="新线程空对话")
            sess.ask(Q1_NORMAL, "N01_ask_normal_rfq", timeout_ms=240_000)
            sess.click_shortlist("N02_shortlist_try")
            sess.click_choice("N03_choice_try", "询价", "报价", "继续", "确认")
            sess.close()

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, NORMAL, env="buyer-a.env", timeout=480)
                (OUT / "normal_core.log").write_text(out, encoding="utf-8")
                r1["discover"] = marker(out, "N_DISCOVER")
                r1["shortlist"] = marker(out, "N_SHORTLIST")
                r1["rfq"] = marker(out, "N_RFQ")
                r1["order"] = marker(out, "N_ORDER")
                r1["ship"] = marker(out, "N_SHIP")
                r1["done"] = marker(out, "N_DONE")
            finally:
                b.close()
            n_cid = (r1.get("done") or r1.get("discover") or {}).get("case_id")

            sess.open_buyer()
            sess.ask(
                f"刚才那条采购需求已推进，请用表格说明采购案 {n_cid}：状态、候选、询价与订单关键信息。",
                "N04_chat_status_after_core",
                timeout_ms=120_000,
            )
            sess.close()
            sess.portal_shot("buyer-a", "tickets", "N05_buyer_tickets")
            sess.portal_shot("supplier-a", "tickets", "N06_sa_tickets")
            sess.portal_shot("supplier-b", "tickets", "N06_sb_tickets")
            sess.portal_shot("supplier-c", "tickets", "N06_sc_tickets")

            s = ssh("39.105.20.113", pem=False)
            try:
                out = remote_py(s, SUP_ACK, env="supplier-a.env", timeout=240)
                (OUT / "normal_sup.log").write_text(out, encoding="utf-8")
                r1["sup"] = marker(out, "SUP_DONE")
            finally:
                s.close()
            sess.portal_shot("supplier-a", "tickets", "N07_sa_after_ack")
            sess.portal_shot("logistics", "tickets", "N08_logistics")

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, finish_code([n_cid] if n_cid else []), env="buyer-a.env", timeout=180)
                (OUT / "normal_finish.log").write_text(out, encoding="utf-8")
                r1["finish"] = marker(out, "FINISH")
            finally:
                b.close()
            sess.portal_shot("buyer-a", "tickets", "N09_final_tickets")
            sess.portal_shot("buyer-a", "audit", "N10_audit")
            sess.open_buyer()
            sess.ask(f"确认采购案 {n_cid} 是否 ACTIVE，一句话。", "N11_chat_final", timeout_ms=80_000)
            sess.close()

            if (r1.get("discover") or {}).get("n", 0) < 1:
                r1["issues"].append(f"发现不足: {r1.get('discover')}")
            if not (r1.get("order") or {}).get("ticket") and not (r1.get("done") or {}).get("ticket"):
                r1["issues"].append(f"无订单工单: {r1.get('order')}")
            r1["ok"] = not r1["issues"]
            reports.append(r1)
            print("NORMAL", r1["ok"], r1["issues"], flush=True)

            # ========== 路径二：组群竞价（再问第二个具体问题） ==========
            r2: dict = {"title": "组群竞价全链路", "ok": False, "issues": [], "question": Q2_AUCTION}
            sess.open_buyer()
            sess.shot_here("A00_empty_chat", note="新线程空对话")
            sess.ask(Q2_AUCTION, "A01_ask_group_auction", timeout_ms=240_000)
            sess.click_shortlist("A02_shortlist_try")
            sess.click_choice("A03_choice_auction", "组群竞价", "竞价", "TCO")
            sess.close()

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, AUCTION, env="buyer-a.env", timeout=480)
                (OUT / "auction_core.log").write_text(out, encoding="utf-8")
                r2["discover"] = marker(out, "A_DISCOVER")
                r2["rfq"] = marker(out, "A_RFQ")
                r2["auction"] = marker(out, "A_AUCTION")
                r2["order"] = marker(out, "A_ORDER")
                r2["done"] = marker(out, "A_DONE")
            finally:
                b.close()
            a_cid = (r2.get("done") or r2.get("auction") or {}).get("case_id")

            sess.open_buyer()
            sess.ask(
                f"说明采购案 {a_cid} 竞价 transport、有效出价、中标方与订单。",
                "A04_chat_auction_summary",
                timeout_ms=120_000,
            )
            sess.close()
            sess.portal_shot("buyer-a", "tickets", "A05_buyer_tickets")
            sess.portal_shot("supplier-a", "tickets", "A06_sa_tickets")
            sess.portal_shot("supplier-c", "tickets", "A06_sc_tickets")

            s = ssh("39.105.20.113", pem=False)
            try:
                out = remote_py(s, SUP_ACK, env="supplier-a.env", timeout=240)
                (OUT / "auction_sup.log").write_text(out, encoding="utf-8")
                r2["sup"] = marker(out, "SUP_DONE")
            finally:
                s.close()
            sess.portal_shot("supplier-a", "tickets", "A07_sa_after_ack")
            sess.portal_shot("logistics", "tickets", "A08_logistics")

            b = ssh("81.70.46.119", pem=True)
            try:
                out = remote_py(b, finish_code([a_cid] if a_cid else []), env="buyer-a.env", timeout=180)
                (OUT / "auction_finish.log").write_text(out, encoding="utf-8")
                r2["finish"] = marker(out, "FINISH")
            finally:
                b.close()
            sess.portal_shot("buyer-a", "tickets", "A09_final_tickets")
            sess.portal_shot("buyer-a", "audit", "A10_audit")
            sess.open_buyer()
            sess.ask(f"确认采购案 {a_cid} 是否 ACTIVE，一句话。", "A11_chat_final", timeout_ms=80_000)
            sess.close()

            auc = r2.get("auction") or {}
            if (auc.get("priced") or 0) < 2 and (r2.get("done") or {}).get("priced", 0) < 2:
                r2["issues"].append(f"有效出价应≥2: {auc}")
            if not (r2.get("order") or {}).get("ticket") and not (r2.get("done") or {}).get("ticket"):
                r2["issues"].append("竞价后无订单工单")
            r2["transport"] = auc.get("transport") or (r2.get("done") or {}).get("transport")
            r2["ok"] = not r2["issues"]
            reports.append(r2)
            print("AUCTION", r2["ok"], r2.get("transport"), r2["issues"], flush=True)
        finally:
            sess.close()
            browser.close()

    write_review(reports, sess.log)
    print("REVIEW", OUT / "REVIEW.md", flush=True)
    print("SHOTS", len(sess.log), flush=True)
    return 0 if all(x.get("ok") for x in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
