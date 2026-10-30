# -*- coding: utf-8 -*-
"""Continue buyer-a UI: confirm shortlist HITL → RFQ, screenshot."""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "chapter5_run" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://ashui.online:8090/"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1200)
        nav = page.locator('button.nav[data-page="chat"]')
        if nav.count():
            nav.first.click()
            page.wait_for_timeout(800)

        # Prefer existing HITL dock; else start fresh discovery turn
        confirm = page.get_by_role("button", name="确认并询价")
        if not confirm.count():
            # also try text contains
            confirm = page.locator("button:has-text('确认并询价')")
        if confirm.count():
            page.screenshot(path=str(OUT / "ui_buyer-a_hitl_before_rfq.png"), full_page=True)
            confirm.first.click()
        else:
            box = page.locator("#chatText")
            box.fill(
                "确认供应商智能体A、B、C三家，发起 AIP 询价，把报价对比结果用表格告诉我。"
            )
            page.locator("#btnSend").click()

        # wait send re-enable
        btn = page.locator("#btnSend")
        deadline = time.time() + 300
        saw = False
        while time.time() < deadline:
            dis = btn.is_disabled()
            if dis:
                saw = True
            elif saw and not dis:
                break
            page.wait_for_timeout(500)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT / "ui_buyer-a_chat_rfq.png"), full_page=True)
        # scroll chat to bottom-ish
        page.evaluate("() => { const el=document.querySelector('#chatMsgs'); if(el) el.scrollTop=el.scrollHeight; }")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / "ui_buyer-a_chat_rfq_bottom.png"), full_page=True)
        meta = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "url": URL,
            "shots": [
                "ui_buyer-a_hitl_before_rfq.png",
                "ui_buyer-a_chat_rfq.png",
                "ui_buyer-a_chat_rfq_bottom.png",
            ],
        }
        (ROOT / "docs/evidence/chapter5_run/ui_buyer_rfq_continue.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("saved rfq shots")
        browser.close()


if __name__ == "__main__":
    main()
