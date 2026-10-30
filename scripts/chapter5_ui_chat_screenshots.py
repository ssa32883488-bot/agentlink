# -*- coding: utf-8 -*-
"""Open live AgentLink consoles in Playwright, drive chat turns, save screenshots.

Outputs → docs/evidence/chapter5_run/screenshots/ui_*.png
"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "chapter5_run" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = ROOT / "docs" / "evidence" / "chapter5_run" / "ui_chat_shots.json"

# Deployed consoles (docs/agent_portals.md)
PORTALS = [
    {
        "id": "buyer-a",
        "url": "https://ashui.online:8090/",
        "has_chat": True,
        "turns": [
            "先看看现在原料库存有没有低于安全线，用表格简要说明。",
            "启动正式采购：产品「重型脚轮」，数量 500，额定载荷至少 300kg。先去梧桐平台发现供应商，不要直接询价。",
        ],
    },
    {
        "id": "buyer-b",
        "url": "https://ashui.online:8092/",
        "has_chat": True,
        "turns": ["你好，请用一句话介绍你能协助完成的采购协同能力。"],
    },
    {
        "id": "supplier-a",
        "url": "http://39.105.20.113:8091/",
        "has_chat": True,
        "turns": ["查看库存与价目，重点说明重型脚轮相关 SKU。"],
    },
    {
        "id": "supplier-b",
        "url": "http://39.105.20.113:8093/",
        "has_chat": True,
        "turns": ["查看库存"],
    },
    {
        "id": "supplier-c",
        "url": "http://39.105.20.113:8094/",
        "has_chat": True,
        "turns": ["查看价目"],
    },
    {
        "id": "logistics",
        "url": "https://ashui.online:8095/",
        "has_chat": False,
        "turns": [],
    },
]


def shot(page, name: str) -> str:
    path = OUT / name
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def wait_chat_idle(page, timeout_ms: int = 180_000) -> None:
    """Wait until send button re-enabled after SSE finishes."""
    btn = page.locator("#btnSend")
    # briefly allow disable after click
    try:
        btn.wait_for(state="visible", timeout=10_000)
    except PwTimeout:
        return
    deadline = time.time() + timeout_ms / 1000
    saw_disabled = False
    while time.time() < deadline:
        disabled = btn.is_disabled()
        if disabled:
            saw_disabled = True
        elif saw_disabled and not disabled:
            page.wait_for_timeout(800)
            return
        page.wait_for_timeout(400)
    # timeout: still capture whatever is on screen


def open_chat_page(page) -> None:
    nav = page.locator('button.nav[data-page="chat"]')
    if nav.count():
        nav.first.click()
        page.wait_for_timeout(600)


def send_turn(page, text: str) -> None:
    box = page.locator("#chatText")
    box.wait_for(state="visible", timeout=15_000)
    box.fill(text)
    page.locator("#btnSend").click()
    wait_chat_idle(page, timeout_ms=240_000)


def run_portal(browser, portal: dict) -> dict:
    item = {
        "id": portal["id"],
        "url": portal["url"],
        "ok": False,
        "shots": [],
        "error": None,
        "turns_done": 0,
    }
    context = browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
    )
    page = context.new_page()
    try:
        page.goto(portal["url"], wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        item["shots"].append(shot(page, f"ui_{portal['id']}_home.png"))

        if portal["has_chat"]:
            open_chat_page(page)
            page.wait_for_timeout(800)
            item["shots"].append(shot(page, f"ui_{portal['id']}_chat_empty.png"))
            for i, turn in enumerate(portal["turns"], 1):
                send_turn(page, turn)
                item["turns_done"] = i
                item["shots"].append(shot(page, f"ui_{portal['id']}_chat_turn{i}.png"))
            # collaboration rail if present
            if page.locator("#collabTimeline").count():
                try:
                    page.locator("#collabTimeline").scroll_into_view_if_needed()
                    page.wait_for_timeout(400)
                    item["shots"].append(shot(page, f"ui_{portal['id']}_collab.png"))
                except Exception:
                    pass
        else:
            # logistics: try mailbox / notify / workbench
            for page_name, sel in [
                ("mailbox", 'button.nav[data-page="mailbox"]'),
                ("notify", 'button.nav[data-page="notify"]'),
                ("workbench", 'button.nav[data-page="workbench"]'),
            ]:
                loc = page.locator(sel)
                if loc.count():
                    loc.first.click()
                    page.wait_for_timeout(1000)
                    item["shots"].append(shot(page, f"ui_{portal['id']}_{page_name}.png"))
                    break
            else:
                item["shots"].append(shot(page, f"ui_{portal['id']}_workspace.png"))

        item["ok"] = True
    except Exception as e:
        item["error"] = f"{e}\n{traceback.format_exc()}"
        try:
            item["shots"].append(shot(page, f"ui_{portal['id']}_error.png"))
        except Exception:
            pass
    finally:
        context.close()
    return item


def main() -> None:
    report = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "portals": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for portal in PORTALS:
                print(f"==> {portal['id']} {portal['url']}", flush=True)
                item = run_portal(browser, portal)
                report["portals"].append(item)
                print(
                    f"    ok={item['ok']} turns={item['turns_done']} shots={len(item['shots'])} err={item['error'] and item['error'][:120]}",
                    flush=True,
                )
        finally:
            browser.close()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report", REPORT)
    ok_n = sum(1 for x in report["portals"] if x["ok"])
    print(f"done {ok_n}/{len(report['portals'])}")


if __name__ == "__main__":
    main()
