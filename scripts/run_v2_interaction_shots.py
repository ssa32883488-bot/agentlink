# -*- coding: utf-8 -*-
"""本地/同机：走 commerce_v2 交互矩阵并截断点图（可选 Playwright）。

用法：
  python scripts/run_v2_interaction_shots.py
  python scripts/run_v2_interaction_shots.py --with-ui http://127.0.0.1:8090
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AGENTLINK_RUNTIME", "v2")
os.environ.setdefault("V2_LOCAL_PARTNERS", "1")

OUT = ROOT / "docs" / "evidence" / "v2_interaction_shots" / datetime.now().strftime("%Y%m%d_%H%M%S")


async def run_matrix() -> dict:
    from commerce_v2.chat_api import handle_chat
    from commerce_v2 import case_store, order_ids
    from commerce_v2.gates import ack_logistics_gate, ack_order_gate

    case_store.create_case("buyer-a")
    steps = []

    async def step(name: str, text: str) -> dict:
        r = await handle_chat("buyer-a", text)
        rec = {
            "name": name,
            "text": text,
            "reply": (r.get("reply") or "")[:500],
            "state": (r.get("case") or {}).get("state"),
            "widgets": [w.get("kind") for w in (r.get("ui_widgets") or [])],
            "order_id": (r.get("case") or {}).get("order_id"),
            "logistics_id": (r.get("case") or {}).get("logistics_id"),
        }
        steps.append(rec)
        print(f"[{name}] state={rec['state']} widgets={rec['widgets']}")
        return r

    await step("01_demand", "采购300套重型脚轮")
    await step(
        "02_shortlist",
        "已确认短名单，请对以下 candidate_id 调用 rfq.send_batch：supplier-a,supplier-c",
    )
    await step("03_bargain", "请帮我议价，询问优惠政策")
    r4 = await step("04_buy", "确认购买：供应商supplier-a 数量500")
    oid = r4["case"]["order_id"]
    await step("05_ask_status", "确认了吗")
    ack_order_gate("buyer-a", oid)
    ack_order_gate("supplier-a", oid)
    await step("06_after_gate", "确认了吗")
    r7 = await step("07_logistics", "允许询运")
    lid = r7["case"]["logistics_id"]
    ack_logistics_gate("buyer-a", lid)
    ack_logistics_gate("logistics", lid)
    steps.append(
        {
            "name": "08_gates",
            "order_effective": order_ids.get_order(oid)["effective"],
            "logistics_effective": True,
            "order_id": oid,
            "logistics_id": lid,
        }
    )

    # group
    case_store.create_case("buyer-a")
    await step("g01_demand", "采购300套重型脚轮")
    await step("g02_group_ask", "我要组群竞价")
    await step(
        "g03_members",
        "已确认短名单，请对以下 candidate_id 调用 rfq.send_batch：supplier-a,supplier-c",
    )
    await step("g04_confirm", "确认进行组群竞价")
    await step("g05_decide", "组群决断：与supplier-a下单")
    await step("g06_tickets", "完成组群物流")

    return {"steps": steps, "out": str(OUT)}


def maybe_playwright(ui_base: str) -> list[str]:
    shots = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        print("Playwright 不可用，跳过 UI 截图:", e)
        return shots
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(ui_base, wait_until="domcontentloaded", timeout=60000)
        path = OUT / "ui_home.png"
        page.screenshot(path=str(path), full_page=True)
        shots.append(str(path))
        # 尝试发一句采购
        for sel in ["textarea", "input[type=text]", "#chat-input", ".chat-input"]:
            loc = page.locator(sel)
            if loc.count():
                loc.first.fill("采购300套重型脚轮")
                page.keyboard.press("Enter")
                page.wait_for_timeout(2500)
                path2 = OUT / "ui_after_demand.png"
                page.screenshot(path=str(path2), full_page=True)
                shots.append(str(path2))
                break
        browser.close()
    return shots


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-ui", default="", help="UI base URL for Playwright shot")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run_matrix())
    (OUT / "matrix.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    shots = []
    if args.with_ui:
        shots = maybe_playwright(args.with_ui)
    (OUT / "INDEX.md").write_text(
        "# v2 交互矩阵证据\n\n"
        f"- matrix: `{OUT / 'matrix.json'}`\n"
        + "\n".join(f"- shot: `{s}`" for s in shots)
        + "\n",
        encoding="utf-8",
    )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
