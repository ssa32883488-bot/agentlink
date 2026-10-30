"""采购商 ERP：销售下单、扣料、通知、对话补货（按 agent_id 分库）。"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from commerce.db import connect, dumps, init_buyer_schema, lock_for, row_to_dict

AGENT = os.getenv("BUYER_AGENT_ID", "buyer-a")


def configure(agent_id: str) -> None:
    """进程内绑定当前采购智能体（A/B 同构，仅库不同）。"""
    global AGENT
    AGENT = (agent_id or "buyer-a").strip() or "buyer-a"
    os.environ["BUYER_AGENT_ID"] = AGENT


def agent_id() -> str:
    return AGENT


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_db() -> None:
    with lock_for(AGENT):
        conn = connect(AGENT)
        init_buyer_schema(conn)
        conn.close()


def list_products() -> list[dict[str, Any]]:
    ensure_db()
    conn = connect(AGENT)
    rows = conn.execute("SELECT * FROM products WHERE active=1").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def list_inventory() -> list[dict[str, Any]]:
    ensure_db()
    conn = connect(AGENT)
    rows = conn.execute(
        """
        SELECT m.code, m.name, m.unit, m.preferred_supplier, m.safety_stock,
               i.on_hand, i.reserved,
               (i.on_hand - i.reserved) AS available
        FROM materials m
        JOIN inventory i ON i.material_code = m.code
        ORDER BY m.code
        """
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = row_to_dict(r) or {}
        d["low"] = float(d["available"]) < float(d["safety_stock"])
        out.append(d)
    return out


def list_sales_orders(limit: int = 50) -> list[dict[str, Any]]:
    ensure_db()
    conn = connect(AGENT)
    rows = conn.execute(
        "SELECT * FROM sales_orders ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def list_notifications(unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    ensure_db()
    conn = connect(AGENT)
    if unread_only:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE read=0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = row_to_dict(r) or {}
        if d.get("payload_json"):
            import json

            d["payload"] = json.loads(d["payload_json"])
        out.append(d)
    return out


def mark_notification_read(nid: str) -> None:
    conn = connect(AGENT)
    conn.execute("UPDATE notifications SET read=1 WHERE id=?", (nid,))
    conn.commit()
    conn.close()


def place_sales_order(
    *,
    sku: str,
    qty: int,
    customer_name: str = "C端用户",
) -> dict[str, Any]:
    """座椅商城下单：写销售单、按BOM扣料、低库存写通知。"""
    if qty <= 0:
        raise ValueError("数量必须大于0")
    ensure_db()
    with lock_for(AGENT):
        conn = connect(AGENT)
        product = conn.execute("SELECT * FROM products WHERE sku=?", (sku,)).fetchone()
        if not product:
            conn.close()
            raise ValueError(f"未知商品 {sku}")
        bom = conn.execute(
            "SELECT material_code, qty_per FROM bom WHERE finished_sku=?", (sku,)
        ).fetchall()
        if not bom:
            conn.close()
            raise ValueError("BOM未配置")

        needs: list[tuple[str, float]] = []
        shortages: list[dict[str, Any]] = []
        for b in bom:
            need = float(b["qty_per"]) * qty
            needs.append((b["material_code"], need))
            inv = conn.execute(
                "SELECT on_hand, reserved FROM inventory WHERE material_code=?",
                (b["material_code"],),
            ).fetchone()
            mat = conn.execute(
                "SELECT name, safety_stock, preferred_supplier, unit FROM materials WHERE code=?",
                (b["material_code"],),
            ).fetchone()
            on_hand = float(inv["on_hand"]) if inv else 0.0
            reserved = float(inv["reserved"]) if inv else 0.0
            available = on_hand - reserved
            # 允许超卖演示原料告警：先扣减到不低于0，不足也记 shortage
            after = available - need
            safety = float(mat["safety_stock"]) if mat else 0
            if after < safety:
                shortages.append(
                    {
                        "material_code": b["material_code"],
                        "name": mat["name"] if mat else b["material_code"],
                        "unit": mat["unit"] if mat else "",
                        "need": need,
                        "available_before": available,
                        "available_after": max(after, 0),
                        "safety_stock": safety,
                        "short_vs_safety": round(safety - max(after, 0), 2),
                        "preferred_supplier": mat["preferred_supplier"] if mat else None,
                    }
                )

        order_id = f"SO-{uuid4().hex[:10]}"
        amount = float(product["price"]) * qty
        conn.execute(
            """INSERT INTO sales_orders(id,created_at,customer_name,sku,qty,amount,status)
               VALUES(?,?,?,?,?,?,?)""",
            (order_id, _now(), customer_name, sku, qty, amount, "confirmed"),
        )
        for code, need in needs:
            conn.execute(
                "INSERT INTO sales_order_lines(order_id,material_code,need_qty) VALUES(?,?,?)",
                (order_id, code, need),
            )
            inv = conn.execute(
                "SELECT on_hand FROM inventory WHERE material_code=?", (code,)
            ).fetchone()
            new_on = max(0.0, float(inv["on_hand"]) - need)
            conn.execute(
                "UPDATE inventory SET on_hand=? WHERE material_code=?", (new_on, code)
            )

        notif = None
        if shortages:
            nid = f"NTF-{uuid4().hex[:10]}"
            title = f"原料不足告警 · 销售单 {order_id}"
            lines = [
                f"{s['name']}（{s['material_code']}）预计剩余 {s['available_after']}{s['unit']}，"
                f"低于安全库存 {s['safety_stock']}，缺口约 {s['short_vs_safety']}{s['unit']}"
                for s in shortages
            ]
            body = f"客户购买 {product['name']} × {qty}。\n" + "\n".join(lines) + "\n可对话：「按缺口询价」或点通知发起补货。"
            payload = {"order_id": order_id, "sku": sku, "qty": qty, "shortages": shortages}
            conn.execute(
                """INSERT INTO notifications(id,created_at,level,title,body,payload_json,read)
                   VALUES(?,?,?,?,?,?,0)""",
                (nid, _now(), "warning", title, body, dumps(payload)),
            )
            tid = f"TASK-{uuid4().hex[:10]}"
            conn.execute(
                """INSERT INTO audit_tasks(id,created_at,kind,title,status,detail_json)
                   VALUES(?,?,?,?,?,?)""",
                (tid, _now(), "shortage_alert", title, "open", dumps(payload)),
            )
            notif = {"id": nid, "title": title, "shortages": shortages}

        conn.commit()
        conn.close()
        return {
            "order_id": order_id,
            "sku": sku,
            "product_name": product["name"],
            "qty": qty,
            "amount": amount,
            "status": "confirmed",
            "notification": notif,
            "shortage_count": len(shortages),
        }


def append_conversation(
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
    *,
    thread_id: str | None = None,
) -> str:
    from commerce import chat_sessions as cs

    ensure_db()
    tid = cs.ensure_thread(AGENT, thread_id)
    cid = f"MSG-{uuid4().hex[:10]}"
    conn = connect(AGENT)
    conn.execute(
        "INSERT INTO conversations(id,created_at,role,content,meta_json,thread_id) VALUES(?,?,?,?,?,?)",
        (cid, _now(), role, content, dumps(meta or {}), tid),
    )
    conn.commit()
    conn.close()
    title = None
    if role == "user" and content.strip():
        title = content.strip().replace("\n", " ")[:36]
    cs.touch_thread(AGENT, tid, title=title)
    return cid


def list_conversations(limit: int = 100, *, thread_id: str | None = None) -> list[dict[str, Any]]:
    from commerce import chat_sessions as cs

    ensure_db()
    tid = thread_id or cs.active_thread_id(AGENT)
    conn = connect(AGENT)
    if tid:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE thread_id=? ORDER BY created_at ASC LIMIT ?",
            (tid, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY created_at ASC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def list_audit_tasks(limit: int = 50) -> list[dict[str, Any]]:
    ensure_db()
    conn = connect(AGENT)
    rows = conn.execute(
        "SELECT * FROM audit_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def latest_shortage_payload() -> dict[str, Any] | None:
    notes = list_notifications(limit=20)
    for n in notes:
        if n.get("level") == "warning" and (n.get("payload") or {}).get("shortages"):
            return n["payload"]
    return None


def materials_for_rfq_from_shortage(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """把缺口转成询价行：按 preferred_supplier 分组。"""
    return list(payload.get("shortages") or [])
