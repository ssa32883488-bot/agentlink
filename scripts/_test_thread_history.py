# -*- coding: utf-8 -*-
"""本地：保存/切换/查看历史对话。"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AGENTLINK_RUNTIME", "v2")
os.environ.setdefault("V2_LOCAL_PARTNERS", "1")

from commerce_v2 import thread_store  # noqa: E402
from commerce_v2.chat_api import handle_chat  # noqa: E402


async def main() -> None:
    # 清掉本测 agent 文件，避免脏数据干扰断言
    p = ROOT / "data" / "v2_threads" / "buyer-a.json"
    if p.exists():
        p.unlink()

    t1 = thread_store.create_thread("buyer-a", title="第一窗")
    r1 = await handle_chat("buyer-a", "采购100套脚轮", thread_id=t1["id"])
    assert r1["thread_id"] == t1["id"], r1
    tid, msgs = thread_store.list_messages("buyer-a", t1["id"])
    assert len(msgs) >= 2 and msgs[0]["role"] == "user", msgs

    t2 = thread_store.create_thread("buyer-a", title="第二窗")
    r2 = await handle_chat("buyer-a", "采购200套脚轮", thread_id=t2["id"])
    assert r2["thread_id"] == t2["id"]
    items = thread_store.list_threads("buyer-a")
    assert len(items) >= 2, items

    thread_store.activate("buyer-a", t1["id"])
    _, m1 = thread_store.list_messages("buyer-a", t1["id"])
    assert "100" in (m1[0].get("content") or ""), m1[0]
    print("THREAD_OK", len(items), "threads;", len(m1), "msgs in t1")

    from fastapi.testclient import TestClient
    from agents.buyer_a.main import app

    c = TestClient(app)
    th = c.post("/api/erp/chat/threads", json={"title": "API窗"}).json()
    print("new", th.get("id"), th.get("title"))
    chat = c.post(
        "/api/erp/chat",
        json={"text": "帮我采购50套脚轮", "thread_id": th["id"]},
    ).json()
    assert chat.get("thread_id") == th["id"], chat
    conv = c.get(f"/api/erp/conversations?thread_id={th['id']}").json()
    print("conv", len(conv.get("items") or []), conv.get("thread_id"))
    assert len(conv.get("items") or []) >= 2
    threads = c.get("/api/erp/chat/threads").json()
    assert any(x["id"] == th["id"] for x in threads.get("items") or [])
    print("API_OK")


if __name__ == "__main__":
    asyncio.run(main())
