# -*- coding: utf-8 -*-
import os
from playwright.sync_api import sync_playwright

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ["NO_PROXY"] = "*"

URLS = [
    ("buyer", "https://81.70.46.119:8090/"),
    ("logistics", "https://81.70.46.119:8095/"),
    ("supplier-a", "http://39.105.20.113:8091/"),
]

JS = """els => els.map(e => ({
  tag: e.tagName,
  id: e.id || '',
  cls: (e.className || '').toString().slice(0, 60),
  text: (e.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 50),
  vis: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)
}))"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--proxy-server=direct://", "--no-proxy-server"])
    for name, url in URLS:
        ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1800)
        print("===", name, url, "===")
        for t in page.eval_on_selector_all("button, a.linkish, .top-actions a, .top-actions button", JS):
            if t["vis"] and (t["text"] or t["id"]):
                print(t)
        out = rf"F:\code\智能体协议\项目开发\agentlink\docs\evidence\_tmp_live_{name}.png"
        page.screenshot(path=out, full_page=False)
        print("SHOT", out)
        ctx.close()
    b.close()
