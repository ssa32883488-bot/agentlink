# -*- coding: utf-8 -*-
"""Render timeline HTML + Playwright screenshots for chapter 5."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "chapter5_run"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)


def html_for(title: str, data: dict) -> str:
    rows = []
    for i, s in enumerate(data.get("timeline") or [], 1):
        summ = s.get("result_summary") or {}
        rows.append(
            f"<tr><td>{i}</td><td>{s.get('step')}</td><td>{'PASS' if s.get('ok') else 'FAIL'}</td>"
            f"<td>{s.get('http_ms')}</td><td><code>{json.dumps(summ, ensure_ascii=False)}</code></td></tr>"
        )
    proto = json.dumps(data.get("protocol") or {}, ensure_ascii=False, indent=2)
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'/>
<title>{title}</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:24px;background:#fff;color:#222}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:20px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #999;padding:8px;vertical-align:top}}
th{{background:#e8eef5}}
.badge{{display:inline-block;padding:4px 10px;background:#e8f5e9;border:1px solid #81c784;border-radius:4px}}
pre{{background:#f7f7f7;padding:12px;border:1px solid #ddd;white-space:pre-wrap}}
.note{{color:#666;font-size:12px}}
</style></head><body>
<h1>{title}</h1>
<p>case_id: <b>{data.get('case_id')}</b> · path: <b>{data.get('path')}</b> ·
<span class='badge'>{'链路完成' if data.get('ok') else '部分失败'}</span></p>
<p class='note'>证据时间线：HTTP调用buyer-a公网API；发现步骤命中梧桐ADP；RFQ经AIP跨云调用供应Partner。</p>
<h2>步骤时序与时延（ms）</h2>
<table><tr><th>#</th><th>步骤</th><th>结果</th><th>HTTP时延ms</th><th>摘要</th></tr>
{''.join(rows)}
</table>
<h2>协议作用面</h2>
<pre>{proto}</pre>
</body></html>"""


def main() -> None:
    normal = json.loads((OUT / "normal_rfq.json").read_text(encoding="utf-8"))
    group = json.loads((OUT / "group_auction.json").read_text(encoding="utf-8"))
    nhtml = OUT / "timeline_normal.html"
    ghtml = OUT / "timeline_group.html"
    nhtml.write_text(html_for("链路一：普通询价（发现→短名单→并行RFQ）", normal), encoding="utf-8")
    ghtml.write_text(html_for("链路二：组群/竞价选商（发现→RFQ→auction→订单草案）", group), encoding="utf-8")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(nhtml.as_uri(), wait_until="networkidle")
        page.screenshot(path=str(SHOT / "timeline_normal.png"), full_page=True)
        page.goto(ghtml.as_uri(), wait_until="networkidle")
        page.screenshot(path=str(SHOT / "timeline_group.png"), full_page=True)
        # Wutong public page (not login-gated screenshots)
        try:
            page.goto("https://wt.ioa.pub/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            page.screenshot(path=str(SHOT / "wutong_portal_public.png"), full_page=True)
        except Exception as e:
            (SHOT / "wutong_portal_public_error.txt").write_text(str(e), encoding="utf-8")
        browser.close()
    print("screenshots ok", list(SHOT.glob("*.png")))


if __name__ == "__main__":
    main()
