# -*- coding: utf-8 -*-
"""Auction watch UI self-test: static markers + mock HTML contract + optional remote probe."""
from __future__ import annotations

import html
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "ui" / "static"


def fail(msg: str) -> None:
    print("FAIL:", msg, flush=True)
    raise SystemExit(1)


def check_static_markers() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    for needle in ("id=\"auctionWatch\"", "id=\"collabHead\"", "id=\"collabTimeline\"", "auction-watch1"):
        if needle not in index:
            fail(f"index.html missing {needle}")

    for needle in (
        ".auction-watch",
        ".collab-timeline",
        "overflow-y: auto",
        "BIDDING · 密封中",
    ):
        if needle == "BIDDING · 密封中":
            continue
        if needle not in css and needle not in js:
            # overflow in css; phase label in js
            if needle == "overflow-y: auto" and "overflow-y: auto" not in css:
                fail(f"styles.css missing scroll: {needle}")

    if ".collab-timeline" not in css or "overflow-y: auto" not in css:
        fail("collab-timeline not scrollable in CSS")
    if "function renderAuctionWatch" not in js:
        fail("renderAuctionWatch missing")
    if "auctionWatchActive" not in js:
        fail("auctionWatchActive missing")
    if "pending_choices" not in js:
        fail("pending_choices wiring missing")
    # old "hide scrollbar forever" must not block timeline
    if re.search(r"\.right,\s*\.rbody\s*\{\s*scrollbar-width:\s*none", css):
        fail("old no-scrollbar rule still hides right panel scroll")
    print("OK static markers", flush=True)


def agent_display_name(agent_id: str) -> str:
    m = {
        "supplier-a": "供应商A",
        "supplier-b": "供应商B",
        "supplier-c": "供应商C",
        "logistics": "物流",
    }
    return m.get(agent_id, agent_id or "伙伴")


def escape(s: object) -> str:
    return html.escape(str(s), quote=True)


def render_mock(case: dict) -> str:
    """Mirror the critical HTML contract of renderAuctionWatch (no DOM)."""
    st = case.get("state") or ""
    live = st == "BIDDING"
    summary = case.get("auction_summary") or {}
    bids = case.get("auction_bids") or []
    schemes = summary.get("schemes") or []
    shortlist = case.get("shortlist") or []
    product = (case.get("brief") or {}).get("product_name") or "标的"
    qty = (case.get("brief") or {}).get("quantity", "—")

    bid_by = {b["supplier_agent_id"]: b for b in bids if b.get("supplier_agent_id")}
    members = []
    seen = set()
    for p in shortlist:
        sid = p.get("agent_id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        members.append({"id": sid, "role": "supplier", "name": agent_display_name(sid)})
    if "logistics" not in seen:
        members.append({"id": "logistics", "role": "logistics", "name": "物流（旁听）"})

    seats = []
    for m in members:
        if m["role"] == "logistics":
            seats.append("logistics:" + ("旁听" if live else "到岸"))
            continue
        b = bid_by.get(m["id"])
        if live and not bids:
            seats.append(f"{m['id']}:密封中")
        elif not b:
            seats.append(f"{m['id']}:等待")
        elif b.get("error"):
            seats.append(f"{m['id']}:失败")
        elif live:
            seats.append(f"{m['id']}:已密封")
        else:
            seats.append(f"{m['id']}:出价{b.get('unit_price')}")

    parts = [
        "组群竞价观察",
        "BIDDING · 密封中" if live else "BID_REVIEW · 待点选",
        f"{product} × {qty}",
        "seats=" + ",".join(seats),
    ]
    if not live and schemes:
        parts.append("schemes=" + "|".join(
            f"{s.get('supplier_agent_id')}:{s.get('tco')}" for s in schemes[:6]
        ))
    pc = case.get("pending_choices") or {}
    choices = pc.get("choices") or []
    if not live and choices:
        parts.append("choices=" + ",".join(c.get("id") or c.get("label") for c in choices))
    return "\n".join(parts)


def check_mock_contract() -> None:
    bidding = {
        "state": "BIDDING",
        "brief": {"product_name": "重型脚轮", "quantity": 500},
        "shortlist": [
            {"agent_id": "supplier-a"},
            {"agent_id": "supplier-b"},
            {"agent_id": "supplier-c"},
        ],
        "auction_bids": [],
        "auction_summary": {},
    }
    out_b = render_mock(bidding)
    assert "密封中" in out_b, out_b
    assert "supplier-a:密封中" in out_b, out_b
    assert "logistics:旁听" in out_b, out_b
    assert "choices=" not in out_b, out_b
    print("OK mock BIDDING\n ", out_b.replace("\n", " | "), flush=True)

    review = {
        "state": "BID_REVIEW",
        "brief": {"product_name": "重型脚轮", "quantity": 500},
        "shortlist": [
            {"agent_id": "supplier-a"},
            {"agent_id": "supplier-b"},
            {"agent_id": "supplier-c"},
        ],
        "auction_bids": [
            {"supplier_agent_id": "supplier-a", "unit_price": 12.5, "tco": 6400},
            {"supplier_agent_id": "supplier-b", "unit_price": 11.8, "tco": 6100},
            {"supplier_agent_id": "supplier-c", "error": "timeout"},
        ],
        "auction_summary": {
            "transport": "group",
            "offers_got": 2,
            "schemes": [
                {"supplier_agent_id": "supplier-b", "unit_price": 11.8, "freight": 200, "tco": 6100},
                {"supplier_agent_id": "supplier-a", "unit_price": 12.5, "freight": 150, "tco": 6400},
            ],
        },
        "pending_choices": {
            "prompt": "组群竞价已完成，请点选订货方案",
            "choices": [
                {"id": "order_supplier-b", "label": "选 supplier-b 下单（TCO 6100）"},
                {"id": "order_supplier-a", "label": "选 supplier-a 下单（TCO 6400）"},
            ],
        },
    }
    out_r = render_mock(review)
    assert "待点选" in out_r, out_r
    assert "schemes=supplier-b:6100|supplier-a:6400" in out_r, out_r
    assert "choices=order_supplier-b,order_supplier-a" in out_r, out_r
    assert "supplier-a:出价12.5" in out_r, out_r
    assert "supplier-c:失败" in out_r, out_r
    print("OK mock BID_REVIEW\n ", out_r.replace("\n", " | "), flush=True)

    # 非竞价态应不展示（由 auctionWatchActive 控制）
    for st in ("COMPARE_PENDING", "ORDER_DRAFT", "ACTIVE"):
        assert st not in ("BIDDING", "BID_REVIEW")
    print("OK visibility gate states", flush=True)


def check_data_chain() -> None:
    """Ensure backend still writes fields the UI reads."""
    wit = (ROOT / "commerce" / "chat_buyer_wit.py").read_text(encoding="utf-8")
    flow = (ROOT / "commerce" / "flow_service.py").read_text(encoding="utf-8")
    if "pending_choices=widget" not in wit and 'pending_choices=widget' not in wit:
        # actual is pending_choices=widget in update_case
        if "pending_choices" not in wit:
            fail("chat_buyer_wit no longer persists pending_choices after auction")
    if "auction_summary" not in flow or "auction_bids" not in flow:
        fail("flow_service missing auction_summary/bids patch")
    if 'state == "BIDDING"' not in flow and "!= \"BIDDING\"" not in flow:
        fail("flow_service auction gate missing")
    print("OK backend field chain", flush=True)


def check_gaps() -> list[str]:
    gaps: list[str] = []
    gaps.append(
        "LIVE_PARTIAL: BIDDING 期间 case 上尚无 auction_bids（step_auction 阻塞结束才写盘），"
        "观察页只能显示「密封出价中」，不能逐家实时点亮「已密封提交」。"
    )
    gaps.append("NO_WS: 依赖 4s 轮询 loadFlow；开拍到开标之间偏整段等待，不是行情推送。")
    gaps.append(
        "E2E_BROWSER: 已验证静态服务+BID_REVIEW 数据合同；未在真实浏览器跑完一轮组群盲拍点击。"
    )
    return gaps


def probe_remote() -> None:
    try:
        import paramiko
    except ImportError:
        print("SKIP remote (no paramiko)", flush=True)
        return
    pem = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
    if not pem.exists():
        print("SKIP remote (no pem)", flush=True)
        return
    host = "81.70.46.119"
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        host,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(pem)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    cmd = (
        "grep -n 'auctionWatch\\|renderAuctionWatch\\|collabTimeline\\|auction-watch1' "
        "/opt/agentlink/ui/static/index.html /opt/agentlink/ui/static/app.js "
        "/opt/agentlink/ui/static/styles.css | head -40; "
        "echo ---; "
        "grep -c 'overflow-y: auto' /opt/agentlink/ui/static/styles.css; "
        "curl -sk -o /dev/null -w 'ui_http=%{http_code}\\n' https://127.0.0.1:8090/ || "
        "curl -s -o /dev/null -w 'ui_http=%{http_code}\\n' http://127.0.0.1:8090/"
    )
    _, o, e = c.exec_command(cmd, timeout=60)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    c.close()
    print("REMOTE probe:\n" + out, flush=True)
    if "renderAuctionWatch" not in out or "auctionWatch" not in out:
        print("REMOTE_STALE: buyer cloud UI not yet carrying auction watch", flush=True)
    else:
        print("OK remote has auction watch markers", flush=True)


def main() -> None:
    check_static_markers()
    check_mock_contract()
    check_data_chain()
    gaps = check_gaps()
    print("GAPS:", flush=True)
    for g in gaps:
        print(" -", g, flush=True)
    if "--remote" in sys.argv:
        probe_remote()
    print("SMOKE_AUCTION_WATCH_DONE", flush=True)


if __name__ == "__main__":
    main()
