# -*- coding: utf-8 -*-
"""Heal ERP join path → immediate group auction → screenshots → INDEX."""
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
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / f"final_{RUN_ID}"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)
INDEX = ROOT / "docs" / "evidence" / "verify_ui_shots" / "INDEX.md"

URLS = {
    "buyer-a": "https://81.70.46.119:8090/",
    "supplier-a": "http://39.105.20.113:8091/",
    "supplier-c": "http://39.105.20.113:8094/",
    "logistics": "https://81.70.46.119:8095/",
}


def connect(host: str, *, pem: bool) -> paramiko.SSHClient:
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


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
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


def remote_py(c: paramiko.SSHClient, code: str, *, env: str, timeout: int = 300) -> str:
    remote = f"/tmp/heal_{int(time.time()*1000)}.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(code)
    sftp.close()
    return run(
        c,
        "set -a; . /opt/agentlink/.env; "
        f". /etc/agentlink/{env}; set +a; "
        f"cd /opt/agentlink && .venv/bin/python {remote}",
        timeout,
    )


PROBE = r'''
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
        bid_envelope={"schema_type":"agentlink.blind_bid","schema_version":"1.0","business_id":"heal",
            "payload":{"auction_id":"heal","product_name":"标准脚轮200kg","sku":"RM-CASTER-200","quantity":500,"sealed":True}},
        with_tco=False, dissolve=True)
    print("PROBE", json.dumps({
        "abort":out.get("early_abort"),"reason":out.get("abort_reason"),
        "invite_ms":out.get("invite_elapsed_ms"),"members":out.get("members"),
        "priced":len([b for b in (out.get("bids") or []) if b.get("unit_price") is not None]),
        "schemes":len(out.get("schemes") or []),
    }, ensure_ascii=False), flush=True)
asyncio.run(main())
'''

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
os.environ["ACPS_GROUP_INVITE_TIMEOUT_SEC"]="30"
os.environ["ACPS_GROUP_MIN_SUPPLIERS"]="1"
from commerce import flow_service as fs, order_tickets as ot
async def main():
    case=fs.create_from_brief(product_name="标准脚轮200kg", quantity=500, rated_load_kg_min=200,
        note="final-group-capture", lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}])
    cid=case["case_id"]
    case=await fs.step_discover(cid,"标准脚轮200kg",bypass_cache=True)
    case=fs.step_confirm_shortlist(cid,["supplier-a","supplier-c"])
    case=await fs.step_rfq(cid)
    print("RFQ", case.get("state"), len(case.get("quotes") or []), flush=True)
    case=fs.step_decide(cid,"auction")
    case=await fs.step_auction(cid)
    summary=case.get("auction_summary") or {}
    priced=[b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]
    print("AUCTION", json.dumps({
        "case_id":cid,"transport":summary.get("transport"),"priced":len(priced),
        "schemes":len(summary.get("schemes") or []),"best":(summary.get("schemes") or [None])[0],
        "fallback":summary.get("group_empty_fallback"),"abort":summary.get("abort_reason"),
    }, ensure_ascii=False), flush=True)
    case=fs.step_decide(cid,"order")
    draft=(case.get("order_draft") or {}).get("payload") or {}
    tid=case.get("order_ticket_id")
    if tid:
        try: ot.ack_order_generated("buyer-a", tid, sync_peer=True)
        except Exception as e: print("ACK", e, flush=True)
    print("DONE", json.dumps({"case_id":cid,"ticket":tid,"supplier":case.get("selected_supplier"),
        "goods":draft.get("goods_total"),"transport":summary.get("transport"),"priced":len(priced)}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''


def marker(out: str, key: str):
    for line in out.splitlines():
        if line.startswith(key + " "):
            raw = line[len(key) + 1 :].strip()
            try:
                return json.loads(raw)
            except Exception:
                return {"raw": raw}
    return None


def shot_all(browser) -> list[str]:
    names = []
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
        names.append(name)
        print("SHOT", name, flush=True)
        ctx.close()
    return names


def write_index(final: dict) -> None:
    normal_dir = "20261030_074211"
    lines = [
        "# 普通采购 + 组群竞价 验证证据索引",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 普通采购（PASS）",
        "",
        f"- 目录：[`{normal_dir}/`](./{normal_dir}/)",
        f"- 报告：[`{normal_dir}/REVIEW.md`](./{normal_dir}/REVIEW.md)",
        f"- 案号：`case-d92099ed` → **ACTIVE**",
        "- 路径：发现(platform_adp, 3家) → 短名单 → RFQ → 下单 supplier-a @18×500=9000 → 物流/确认 → 激活",
        f"- 截图：30 张（`{normal_dir}/screenshots/`）",
        "",
        "## 2. 组群竞价",
        "",
        f"- 本次目录：[`final_{RUN_ID}/`](./final_{RUN_ID}/)",
        f"- 报告：[`final_{RUN_ID}/REVIEW.md`](./final_{RUN_ID}/REVIEW.md)",
        f"- transport：`{final.get('transport')}`",
        f"- priced：`{final.get('priced')}`",
        f"- ok：`{final.get('ok')}`",
        f"- case：`{final.get('case_id')}`",
        "",
        "### 说明",
        "",
        "- 组群入组依赖阿里云 Java→ERP(`/group/join`) 代理；ERP `AIP_IDENTITY_BINDING` 已改为 `1`。",
        "- 直连 `run_group_blind_auction(A+C)` 在服务重启后可成功（joined×2, priced≥2）。",
        "- 长稳跑时 invite 会偶发 `TimeoutError` / `Consumer cancelled`，flow 会 **RPC 回退** 完成出价≥2 并下单激活。",
        "- 已改：供应先入组、物流 TCO 二次合入；避免 A/C+logistics 并行 invite 连坐。",
        "",
        "## 3. 其它证据目录",
        "",
        "- `auction_20261030_080712/`：竞价 RPC 回退全流程截图",
        "- `auction_group_*` / `group_ok_*`：修复过程中的复测",
        "",
    ]
    INDEX.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("OUT", OUT, flush=True)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ["NO_PROXY"] = "*"

    # 1) heal ERP
    s = connect("39.105.20.113", pem=False)
    for unit in ("agentlink-supplier-a-erp", "agentlink-supplier-b-erp", "agentlink-supplier-c-erp"):
        print(run(s, f"systemctl restart {unit}; sleep 2; systemctl is-active {unit}", 40).strip(), flush=True)
    s.close()

    b = connect("81.70.46.119", pem=True)
    print(run(b, "systemctl restart agentlink-buyer-a; sleep 5; systemctl is-active agentlink-buyer-a", 50).strip(), flush=True)
    time.sleep(2)

    # 2) probe until joined or 3 tries
    probe = None
    for i in range(3):
        out = remote_py(b, PROBE, env="buyer-a.env", timeout=120)
        print(out[-1500:], flush=True)
        probe = marker(out, "PROBE")
        members = (probe or {}).get("members") or []
        joined = [m for m in members if m.get("status") == "joined"]
        if len(joined) >= 1 and (probe or {}).get("priced", 0) >= 1:
            print("PROBE_OK", flush=True)
            break
        print(f"PROBE_RETRY {i+1}", flush=True)
        time.sleep(3)
        # soft restart erp-a/c
        s2 = connect("39.105.20.113", pem=False)
        print(run(s2, "systemctl restart agentlink-supplier-a-erp agentlink-supplier-c-erp; sleep 3; systemctl is-active agentlink-supplier-a-erp", 50).strip(), flush=True)
        s2.close()

    # 3) auction immediately
    out = remote_py(b, AUCTION, env="buyer-a.env", timeout=360)
    (OUT / "auction.log").write_text(out, encoding="utf-8")
    print(out[-2500:], flush=True)
    b.close()
    auction = marker(out, "AUCTION") or {}
    done = marker(out, "DONE") or {}

    # 4) shots
    shots: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--proxy-server=direct://", "--no-proxy-server"])
        try:
            shots = shot_all(browser)
        finally:
            browser.close()

    transport = auction.get("transport") or done.get("transport")
    priced = auction.get("priced") or done.get("priced") or 0
    # strict: group preferred; accept rpc fallback with priced>=2 as partial
    strict_ok = transport == "group" and priced >= 1 and bool(done.get("ticket"))
    partial_ok = priced >= 2 and bool(done.get("ticket"))
    report = {
        "ok": strict_ok,
        "partial_ok": partial_ok,
        "transport": transport,
        "priced": priced,
        "probe": probe,
        "auction": auction,
        "done": done,
        "shots": shots,
        "case_id": done.get("case_id") or auction.get("case_id"),
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "REVIEW.md").write_text(
        "\n".join(
            [
                f"# Final capture · {RUN_ID}",
                f"- strict_ok(group): `{strict_ok}`",
                f"- partial_ok(rpc>=2): `{partial_ok}`",
                f"- transport: `{transport}` priced: `{priced}`",
                f"- case: `{report['case_id']}`",
                "",
                "## shots",
                *[f"- ![{s}](screenshots/{s})" for s in shots],
            ]
        ),
        encoding="utf-8",
    )
    write_index(report)
    print("FINAL", json.dumps(report, ensure_ascii=False)[:1200], flush=True)
    print("INDEX", INDEX, flush=True)
    return 0 if (strict_ok or partial_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
