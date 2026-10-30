# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_ROOT = Path(__file__).resolve().parents[1] / "data" / "v2_orders"
_ROOT.mkdir(parents=True, exist_ok=True)


def _path() -> Path:
    return _ROOT / "orders.json"


def _load() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"orders": {}, "logistics": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"orders": {}, "logistics": {}}


def _save(data: dict[str, Any]) -> None:
    _path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def new_order_id(case_id: str, supplier_id: str, sku: str) -> str:
    return f"ord-{case_id[-8:]}-{supplier_id}-{sku}"


def new_logistics_id(order_id: str) -> str:
    return f"log-{order_id}"


def put_order(order: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        data = _load()
        data["orders"][order["order_id"]] = order
        _save(data)
        return json.loads(json.dumps(order))


def get_order(order_id: str) -> dict[str, Any] | None:
    with _LOCK:
        o = _load()["orders"].get(order_id)
        return json.loads(json.dumps(o)) if o else None


def ack_order(order_id: str, *, who: str) -> dict[str, Any]:
    with _LOCK:
        data = _load()
        o = data["orders"].get(order_id)
        if not o:
            raise KeyError(order_id)
        if who == "buyer":
            o["buyer_ack"] = True
        elif who == "supplier":
            o["supplier_ack"] = True
        o["effective"] = bool(o.get("buyer_ack") and o.get("supplier_ack"))
        data["orders"][order_id] = o
        _save(data)
        return json.loads(json.dumps(o))


def put_logistics(row: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        data = _load()
        data["logistics"][row["logistics_id"]] = row
        _save(data)
        return json.loads(json.dumps(row))


def ack_logistics(logistics_id: str, *, who: str) -> dict[str, Any]:
    with _LOCK:
        data = _load()
        o = data["logistics"].get(logistics_id)
        if not o:
            raise KeyError(logistics_id)
        if who == "buyer":
            o["buyer_ack"] = True
        elif who == "logistics":
            o["logistics_ack"] = True
        o["effective"] = bool(o.get("buyer_ack") and o.get("logistics_ack"))
        data["logistics"][logistics_id] = o
        _save(data)
        return json.loads(json.dumps(o))


def list_open_tickets(agent_id: str) -> list[dict[str, Any]]:
    """给 UI 工单列表用的投影。"""
    with _LOCK:
        data = _load()
        items = []
        for o in data["orders"].values():
            if agent_id.startswith("buyer") and o.get("buyer_id") == agent_id:
                items.append(_as_ticket(o, kind="order"))
            if agent_id.startswith("supplier") and o.get("supplier_id") == agent_id:
                items.append(_as_ticket(o, kind="order"))
        for lg in data["logistics"].values():
            if agent_id.startswith("buyer") and lg.get("buyer_id") == agent_id:
                items.append(_as_ticket(lg, kind="logistics_order"))
            if agent_id == "logistics":
                items.append(_as_ticket(lg, kind="logistics_order"))
            if agent_id.startswith("supplier") and lg.get("supplier_id") == agent_id:
                items.append(_as_ticket(lg, kind="logistics_order"))
        return items


def _as_ticket(row: dict[str, Any], *, kind: str) -> dict[str, Any]:
    # 物流单同时带 order_id 与 logistics_id；工单 id 必须用 logistics_id，
    # 否则 UI 用 order_id 调 ack-logistics 会 404 logistics not found
    if kind == "logistics_order":
        oid = row.get("logistics_id") or row.get("order_id")
    else:
        oid = row.get("order_id") or row.get("logistics_id")
    eff = bool(row.get("effective"))
    return {
        "id": oid,
        "kind": kind,
        "status": "closed" if eff else "open",
        "title": row.get("title") or oid,
        "order_id": row.get("order_id"),
        "logistics_id": row.get("logistics_id") if kind == "logistics_order" else None,
        "peer_agent_id": ("logistics" if kind == "logistics_order" else (row.get("supplier_id") or row.get("buyer_id"))),
        "case_id": row.get("case_id"),
        "state": {
            "buyer_order_ack": row.get("buyer_ack") if kind == "order" else None,
            "supplier_order_ack": row.get("supplier_ack") if kind == "order" else None,
            "order_effective": row.get("effective") if kind == "order" else None,
            "logistics_effective": row.get("effective") if kind != "order" else None,
            "buyer_logistics_ack": row.get("buyer_ack") if kind != "order" else None,
            "logistics_ack": row.get("logistics_ack") if kind != "order" else None,
            # UI 兼容旧字段名
            "logistics_agent_ack": row.get("logistics_ack") if kind != "order" else None,
            "effective": eff,
            "buyer_agent_id": row.get("buyer_id"),
        },
        "payload": row,
    }


def mint_uuid() -> str:
    return uuid.uuid4().hex[:10]
