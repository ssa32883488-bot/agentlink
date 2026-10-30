# -*- coding: utf-8 -*-
from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class Phase(str, Enum):
    IDLE = "IDLE"
    SHORTLIST_PENDING = "SHORTLIST_PENDING"
    RFQ_DONE = "RFQ_DONE"
    BARGAIN_ASK = "BARGAIN_ASK"
    BARGAIN_DONE = "BARGAIN_DONE"
    BUY_ASK = "BUY_ASK"
    ORDER_DRAFT = "ORDER_DRAFT"
    ORDER_PEER_PENDING = "ORDER_PEER_PENDING"
    ORDER_EFFECTIVE = "ORDER_EFFECTIVE"
    LOGISTICS_HINT = "LOGISTICS_HINT"
    LOGISTICS_SCHEMA = "LOGISTICS_SCHEMA"
    LOGISTICS_PENDING = "LOGISTICS_PENDING"
    ACTIVE = "ACTIVE"
    # group
    GROUP_SUGGEST = "GROUP_SUGGEST"
    GROUP_ASK = "GROUP_ASK"
    GROUP_BIDDING = "GROUP_BIDDING"
    GROUP_DECIDE = "GROUP_DECIDE"
    GROUP_LOGISTICS = "GROUP_LOGISTICS"
    GROUP_TICKETS = "GROUP_TICKETS"


class Choice(TypedDict, total=False):
    id: str
    label: str
    message: str
    hint: str
    primary: bool


def empty_case(agent_id: str, *, path: str = "normal") -> dict[str, Any]:
    return {
        "case_id": "",
        "agent_id": agent_id,
        "path": path,  # normal | group
        "state": Phase.IDLE.value,
        "brief": {},
        "rewritten_query": "",
        "candidates": [],
        "selected": [],
        "quotes": [],
        "bargain_quotes": [],
        "pending_choices": None,
        "hitl_pending": None,
        "order": None,
        "order_id": None,
        "buyer_order_ack": False,
        "supplier_order_ack": False,
        "logistics": None,
        "logistics_id": None,
        "buyer_logistics_ack": False,
        "logistics_ack": False,
        "group": None,
        "conflict_signals": [],
        "discovery_meta": {"source": "v2"},
        "history": [],
        "runtime": "v2",
    }
