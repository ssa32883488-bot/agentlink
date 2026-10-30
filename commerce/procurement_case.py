"""采购案状态机（对齐指导书 §4.3）。按采购智能体分文件隔离。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_ROOT = Path(__file__).resolve().parents[1]


def _store_path() -> Path:
    agent = (os.getenv("BUYER_AGENT_ID") or "buyer-a").strip() or "buyer-a"
    safe = "".join(c for c in agent if c.isalnum() or c in "-_") or "buyer-a"
    return _ROOT / "data" / f"procurement_cases_{safe}.json"


# 兼容旧路径：若仅有旧文件且新文件不存在，首次读取时由 _load 迁移
_LEGACY = _ROOT / "data" / "procurement_cases.json"

STATES = (
    "DRAFT",
    "DISCOVERING",
    "SHORTLIST_PENDING",
    "SOURCING",
    "COMPARE_PENDING",
    "NEGOTIATING",
    "NEGOTIATE_REVIEW",
    "BIDDING",
    "BID_REVIEW",
    "ORDER_DRAFT",
    "CONTRACT_PENDING",
    "ACTIVE",
    "CLOSED",
    "EXCEPTION",
)

ALLOWED = {
    "DRAFT": {"DISCOVERING", "EXCEPTION"},
    "DISCOVERING": {"SHORTLIST_PENDING", "EXCEPTION"},
    "SHORTLIST_PENDING": {"SOURCING", "DISCOVERING", "EXCEPTION"},
    "SOURCING": {"COMPARE_PENDING", "EXCEPTION"},
    "COMPARE_PENDING": {"NEGOTIATING", "BIDDING", "ORDER_DRAFT", "EXCEPTION"},
    "NEGOTIATING": {"NEGOTIATE_REVIEW", "EXCEPTION"},
    "NEGOTIATE_REVIEW": {"BIDDING", "ORDER_DRAFT", "NEGOTIATING", "EXCEPTION"},
    "BIDDING": {"BID_REVIEW", "EXCEPTION"},
    "BID_REVIEW": {"ORDER_DRAFT", "BIDDING", "EXCEPTION"},
    "ORDER_DRAFT": {"CONTRACT_PENDING", "EXCEPTION"},
    "CONTRACT_PENDING": {"ACTIVE", "ORDER_DRAFT", "EXCEPTION"},
    "ACTIVE": {"CLOSED", "EXCEPTION"},
}

# 每个状态：谁在干活、甲乙方角色、当前业务焦点（供 Wit / UI / flow.status 对齐）
# party_a = 采购方（本域 buyer）；party_b = 对端供应/物流（按焦点变化）
STATE_FOCUS: dict[str, dict[str, str]] = {
    "DRAFT": {
        "actor": "buyer",
        "party_a": "buyer",
        "party_b": "—",
        "focus": "整理整案需求（可多物料），尚未对外",
    },
    "DISCOVERING": {
        "actor": "buyer",
        "party_a": "buyer",
        "party_b": "platform_adp",
        "focus": "带着全部需求问：谁可能覆盖？",
    },
    "SHORTLIST_PENDING": {
        "actor": "buyer_human",
        "party_a": "buyer",
        "party_b": "candidate_suppliers",
        "focus": "人确认短名单（仍是整案，未拆单）",
    },
    "SOURCING": {
        "actor": "buyer",
        "party_a": "buyer",
        "party_b": "shortlist_suppliers",
        "focus": "向短名单统一询价，探各家对每行需求的供货能力",
    },
    "COMPARE_PENDING": {
        "actor": "buyer_human",
        "party_a": "buyer",
        "party_b": "quoting_suppliers",
        "focus": "对照覆盖面：一家全包 / 分单 / 或多方可比进入竞价",
    },
    "NEGOTIATING": {
        "actor": "buyer",
        "party_a": "buyer",
        "party_b": "selected_suppliers",
        "focus": "甲方向选定乙方议价（按物料/供方分别谈）",
    },
    "NEGOTIATE_REVIEW": {
        "actor": "buyer_human",
        "party_a": "buyer",
        "party_b": "selected_suppliers",
        "focus": "人审方案后再选：下单 / 再议 / 竞价",
    },
    "BIDDING": {
        "actor": "buyer",
        "party_a": "buyer",
        "party_b": "auction_group",
        "focus": "多方组群盲拍（仅当同一需求多家可比）",
    },
    "BID_REVIEW": {
        "actor": "buyer_human",
        "party_a": "buyer",
        "party_b": "auction_group",
        "focus": "人按 TCO/方案选定中标供方与物料行",
    },
    "ORDER_DRAFT": {
        "actor": "buyer",
        "party_a": "buyer",
        "party_b": "selected_supplier",
        "focus": "本单仅含该供方承接的物料行（拆单后一供一方一单）",
    },
    "CONTRACT_PENDING": {
        "actor": "both",
        "party_a": "buyer",
        "party_b": "selected_supplier",
        "focus": "甲乙双方确认本单（订单/发票），勿串其它物料",
    },
    "ACTIVE": {
        "actor": "both",
        "party_a": "buyer",
        "party_b": "selected_supplier",
        "focus": "本单已激活履约",
    },
    "CLOSED": {
        "actor": "—",
        "party_a": "buyer",
        "party_b": "selected_supplier",
        "focus": "结案",
    },
    "EXCEPTION": {
        "actor": "buyer_human",
        "party_a": "buyer",
        "party_b": "—",
        "focus": "异常待人处理；先分清卡在哪一甲乙关系",
    },
}


def describe_state_focus(case: dict[str, Any] | None) -> dict[str, Any]:
    """给智能体/UI：当前状态在干什么、甲方乙方是谁、本单焦点物料。"""
    if not case:
        return {"state": None, "party_a": "buyer", "party_b": "—", "focus": "无活跃案"}
    state = str(case.get("state") or "")
    base = dict(STATE_FOCUS.get(state) or {"actor": "?", "party_a": "buyer", "party_b": "?", "focus": state})
    brief = case.get("brief") or {}
    lines = [x for x in (brief.get("lines") or []) if isinstance(x, dict)]
    draft = (case.get("order_draft") or {}).get("payload") or case.get("order_draft") or {}
    if not isinstance(draft, dict):
        draft = {}
    selected = case.get("selected_supplier")
    party_b = selected or base.get("party_b")
    order_line = draft.get("product_name") or draft.get("sku")
    demand = brief.get("product_name")
    if lines:
        demand = " + ".join(
            f"{x.get('name') or x.get('sku')}×{x.get('qty') or '?'}" for x in lines[:6]
        )
    return {
        "case_id": case.get("case_id"),
        "state": state,
        "actor": base.get("actor"),
        "party_a": "buyer（采购甲方）",
        "party_b": f"{party_b}（供应/物流乙方）" if party_b and party_b != "—" else "—",
        "party_b_agent_id": selected,
        "focus": base.get("focus"),
        "demand_scope": demand,  # 整案需求（可多物料）
        "order_line": order_line,  # 当前订单草案只含这一行（拆单后）
        "sku": draft.get("sku") or brief.get("selected_line_sku"),
        "combo": bool(brief.get("combo") or len(lines) >= 2),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(data: Any) -> dict[str, Any]:
    """统一为 {\"cases\": {case_id: case}}；兼容误写成 [] / 缺字段。"""
    if isinstance(data, dict) and isinstance(data.get("cases"), dict):
        return data
    if isinstance(data, dict) and not data:
        return {"cases": {}}
    if isinstance(data, list):
        cases: dict[str, Any] = {}
        for item in data:
            if isinstance(item, dict) and item.get("case_id"):
                cases[str(item["case_id"])] = item
        return {"cases": cases}
    return {"cases": {}}


def _load() -> dict[str, Any]:
    path = _store_path()
    if not path.is_file():
        # buyer-a 兼容迁移旧聚合文件
        agent = (os.getenv("BUYER_AGENT_ID") or "buyer-a").strip()
        if agent == "buyer-a" and _LEGACY.is_file():
            data = _normalize(json.loads(_LEGACY.read_text(encoding="utf-8")))
            _save(data)
            return data
        return {"cases": {}}
    raw = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw) if raw.strip() else {"cases": {}}
    except json.JSONDecodeError:
        parsed = {"cases": {}}
    data = _normalize(parsed)
    # 若文件曾被写成 [] / 非法结构，写回正确形状
    if not (isinstance(parsed, dict) and isinstance(parsed.get("cases"), dict)):
        _save(data)
    return data


def _save(data: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_normalize(data), ensure_ascii=False, indent=2), encoding="utf-8")


def create_case(*, brief: dict[str, Any], created_by: str | None = None) -> dict[str, Any]:
    created_by = created_by or (os.getenv("BUYER_AGENT_ID") or "buyer-a")
    case_id = f"case-{uuid4().hex[:8]}"
    case = {
        "case_id": case_id,
        "state": "DRAFT",
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": created_by,
        "brief": brief,
        "candidates": [],
        "shortlist": [],
        "shortlist_confirmed": False,
        "quotes": [],
        "comparison": None,
        "decision": None,
        "negotiate_goal": None,
        "negotiate_rounds": [],
        "auction_bids": [],
        "selected_supplier": None,
        "order_draft": None,
        "shipping_quote": None,
        "contract": None,
        "buyer_confirmed": False,
        "supplier_confirmed": False,
        "audit": [{"at": _now(), "event": "created", "state": "DRAFT"}],
        "hitl_pending": None,
    }
    data = _load()
    data["cases"][case_id] = case
    _save(data)
    return case


def get_case(case_id: str) -> dict[str, Any] | None:
    return _load()["cases"].get(case_id)


def list_cases(limit: int = 50) -> list[dict[str, Any]]:
    cases = list(_load()["cases"].values())
    cases.sort(key=lambda c: c.get("updated_at") or "", reverse=True)
    return cases[:limit]


def transition(case_id: str, new_state: str, *, event: str, patch: dict[str, Any] | None = None) -> dict[str, Any]:
    data = _load()
    case = data["cases"].get(case_id)
    if not case:
        raise KeyError(case_id)
    cur = case["state"]
    if new_state not in ALLOWED.get(cur, set()) and new_state != cur:
        raise ValueError(f"非法状态迁移 {cur} → {new_state}")
    case["state"] = new_state
    case["updated_at"] = _now()
    if patch:
        case.update(patch)
    case.setdefault("audit", []).append({"at": _now(), "event": event, "state": new_state})
    data["cases"][case_id] = case
    _save(data)
    return case


def update_case(case_id: str, **fields: Any) -> dict[str, Any]:
    data = _load()
    case = data["cases"].get(case_id)
    if not case:
        raise KeyError(case_id)
    case.update(fields)
    case["updated_at"] = _now()
    data["cases"][case_id] = case
    _save(data)
    return case
