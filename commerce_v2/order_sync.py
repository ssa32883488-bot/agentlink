# -*- coding: utf-8 -*-
"""双云工单同步：采购云写单后推到供应云；任一方 Gate 确认后回写对端。"""
from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from typing import Any

from commerce_v2 import order_ids

log = logging.getLogger("commerce_v2.order_sync")

_CTX = ssl._create_unverified_context()


def apply_order(order: dict[str, Any], *, require_place_on_for_create: bool = False) -> dict[str, Any]:
    """写入/合并货单。

    require_place_on_for_create=True 时（供应侧 sync/工具）：新建必须 place_order=on；
    已有单的确认态回写不要求 on。采购本机 put_order 不经此门禁。
    """
    if not order or not order.get("order_id"):
        raise ValueError("order_id required")
    oid = str(order.get("order_id"))
    if require_place_on_for_create and order_ids.get_order(oid) is None:
        from commerce_v2.supplier_tools import is_place_order_on

        if not is_place_order_on(order.get("place_order")):
            raise ValueError("place_order must be on to create supplier order")
    saved = order_ids.put_order(order)
    # 供应侧最后确认时，采购云靠 sync 落单；此处把案推进到「询物流」提醒
    try:
        _promote_buyer_case_for_order(saved)
    except Exception as e:  # noqa: BLE001
        log.warning("promote buyer case after order sync failed: %s", e)
    return saved


def _promote_buyer_case_for_order(order: dict[str, Any]) -> None:
    buyer_id = order.get("buyer_id") or ""
    case_id = order.get("case_id")
    if not buyer_id.startswith("buyer"):
        return
    from commerce_v2 import case_store, thread_store
    from commerce_v2.ask_user import set_ask
    from commerce_v2.models import Phase

    case = case_store.get_case(buyer_id, case_id)
    if not case or case.get("order_id") != order.get("order_id"):
        return
    case["buyer_order_ack"] = bool(order.get("buyer_ack"))
    case["supplier_order_ack"] = bool(order.get("supplier_ack"))
    case["order"] = order
    if order.get("effective") and not case.get("logistics_id"):
        if case.get("path") == "group":
            case["state"] = Phase.ORDER_EFFECTIVE.value
        else:
            already = (case.get("pending_choices") or {}).get("id") == "logistics_hint" or any(
                c.get("id") == "logistics_go"
                for c in ((case.get("pending_choices") or {}).get("choices") or [])
            )
            case["state"] = Phase.LOGISTICS_HINT.value
            if not already:
                set_ask(
                    case,
                    "货单已双方确认生效。是否去询物流？",
                    [
                        {
                            "id": "logistics_go",
                            "label": "去和物流询价下单",
                            "message": "允许询运",
                            "primary": True,
                        }
                    ],
                )
                tip = (
                    f"货单 `{order.get('order_id')}` 已双方确认生效。\n"
                    f"下一步请确认是否建立物流单（询运/下运单）。"
                )
                case_store.append_history(case, "assistant", tip)
                # 写入当前活动线程，切页回对话可见
                tid = thread_store.active_thread_id(buyer_id)
                if tid:
                    thread_store.append_messages(
                        buyer_id,
                        tid,
                        [
                            {
                                "role": "assistant",
                                "content": tip,
                                "meta": {
                                    "case_id": case.get("case_id"),
                                    "thread_id": tid,
                                    "state": case.get("state"),
                                    "ui_widgets": [case.get("pending_choices")]
                                    if case.get("pending_choices")
                                    else [],
                                    "engine": "commerce_v2",
                                },
                            }
                        ],
                    )
        case_store.save_case(case)
    elif not order.get("effective"):
        case["state"] = Phase.ORDER_PEER_PENDING.value
        case_store.save_case(case)


def apply_logistics(row: dict[str, Any]) -> dict[str, Any]:
    if not row or not row.get("logistics_id"):
        raise ValueError("logistics_id required")
    return order_ids.put_logistics(row)


def _http_base(agent_id: str) -> str:
    """agent → https://host:port（无 /rpc）。"""
    from commerce_v2.catalog import _rpc

    rpc = _rpc(agent_id)
    if rpc.endswith("/rpc"):
        return rpc[: -len("/rpc")]
    return rpc.rstrip("/")


def _post_json(url: str, body: dict[str, Any], *, timeout: float = 12.0) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _is_loopback(url: str) -> bool:
    u = (url or "").lower()
    return "127.0.0.1" in u or "localhost" in u


def push_order_to(agent_id: str, order: dict[str, Any], *, require_place_on: bool = False) -> bool:
    """把整单推到对端 agent 的本地 order_ids。失败只打日志。

    require_place_on：首次下单推供应时为 True（用户明确下单）；确认态回写为 False。
    """
    if not agent_id or not order:
        return False
    payload = dict(order)
    if require_place_on:
        payload["place_order"] = "on"
    base = _http_base(agent_id)
    # 本机同仓：buyer/logistics 同机共享 data/v2_orders
    if _is_loopback(base) or os.getenv("V2_LOCAL_PARTNERS", "0") == "1":
        try:
            # 供应 id 本机回退：新建须 on；采购本机合并不强制
            need = require_place_on or str(agent_id).startswith("supplier")
            apply_order(payload, require_place_on_for_create=need)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("local apply_order failed: %s", e)
            return False
    url = f"{base}/api/erp/v2/orders/sync"
    try:
        _post_json(url, {"order": payload, "place_order": payload.get("place_order")})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("push_order_to %s failed: %s", agent_id, e)
        return False


def push_logistics_to(agent_id: str, row: dict[str, Any]) -> bool:
    if not agent_id or not row:
        return False
    base = _http_base(agent_id)
    if _is_loopback(base) or os.getenv("V2_LOCAL_PARTNERS", "0") == "1":
        try:
            apply_logistics(row)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("local apply_logistics failed: %s", e)
            return False
    url = f"{base}/api/erp/v2/logistics/sync"
    try:
        _post_json(url, {"logistics": row})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("push_logistics_to %s failed: %s", agent_id, e)
        return False


def sync_order_peers(order: dict[str, Any], *, from_agent: str) -> None:
    """确认/下单后，把最新态推给买卖双方中「不是自己」的那一侧。"""
    buyer = order.get("buyer_id") or ""
    supplier = order.get("supplier_id") or ""
    if buyer and buyer != from_agent:
        push_order_to(buyer, order)
    if supplier and supplier != from_agent:
        push_order_to(supplier, order)


def sync_logistics_peers(row: dict[str, Any], *, from_agent: str) -> None:
    buyer = row.get("buyer_id") or ""
    if buyer and buyer != from_agent:
        push_logistics_to(buyer, row)
    if from_agent != "logistics":
        push_logistics_to("logistics", row)
