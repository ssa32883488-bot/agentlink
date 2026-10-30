# -*- coding: utf-8 -*-
"""Gate：只写确认态，不产生 AskUser。"""
from __future__ import annotations

from typing import Any

from commerce_v2 import case_store, order_ids, order_sync
from commerce_v2.ask_user import set_ask
from commerce_v2.models import Phase


def ack_order_gate(agent_id: str, order_id: str) -> dict[str, Any]:
    who = "buyer" if agent_id.startswith("buyer") else "supplier"
    o = order_ids.ack_order(order_id, who=who)
    # 同步到 case（仅采购云有 case）
    buyer_id = o.get("buyer_id") or (agent_id if agent_id.startswith("buyer") else None)
    case = case_store.get_case(buyer_id, o.get("case_id")) if buyer_id else None
    if case and case.get("order_id") == order_id:
        case["buyer_order_ack"] = bool(o.get("buyer_ack"))
        case["supplier_order_ack"] = bool(o.get("supplier_ack"))
        case["order"] = o
        if o.get("effective"):
            case["state"] = Phase.ORDER_EFFECTIVE.value
            if case.get("path") != "group" and not case.get("logistics_id"):
                case["state"] = Phase.LOGISTICS_HINT.value
                w = set_ask(
                    case,
                    "货单已双方确认生效。是否去询物流？",
                    [{"id": "logistics_go", "label": "去和物流询价下单", "message": "允许询运", "primary": True}],
                )
                tip = (
                    f"货单 `{order_id}` 已双方确认生效。\n"
                    f"下一步请确认是否建立物流单（询运/下运单）。"
                )
                case_store.append_history(case, "assistant", tip)
                try:
                    from commerce_v2 import thread_store

                    tid = thread_store.active_thread_id(buyer_id or agent_id)
                    if tid:
                        thread_store.append_messages(
                            buyer_id or agent_id,
                            tid,
                            [
                                {
                                    "role": "assistant",
                                    "content": tip,
                                    "meta": {
                                        "case_id": case.get("case_id"),
                                        "thread_id": tid,
                                        "state": case.get("state"),
                                        "ui_widgets": [w] if w else [],
                                        "engine": "commerce_v2",
                                    },
                                }
                            ],
                        )
                except Exception:
                    pass
        else:
            case["state"] = Phase.ORDER_PEER_PENDING.value
        case_store.save_case(case)
    # 跨云：把最新确认态推给对端；采购云 apply_order 会补「询物流」AskUser
    order_sync.sync_order_peers(o, from_agent=agent_id)
    return {"ok": True, "order": o, "who": who, "case_state": (case or {}).get("state") if case else None}


def ack_logistics_gate(agent_id: str, logistics_id: str) -> dict[str, Any]:
    who = "buyer" if agent_id.startswith("buyer") else "logistics"
    row = order_ids.ack_logistics(logistics_id, who=who)
    buyer_id = row.get("buyer_id")
    case = case_store.get_case(buyer_id) if buyer_id else None
    if case and case.get("logistics_id") == logistics_id:
        case["logistics"] = row
        case["buyer_logistics_ack"] = bool(row.get("buyer_ack"))
        case["logistics_ack"] = bool(row.get("logistics_ack"))
        if row.get("effective"):
            case["state"] = Phase.ACTIVE.value
        case_store.save_case(case)
    order_sync.sync_logistics_peers(row, from_agent=agent_id)
    return {"ok": True, "logistics": row, "who": who}
