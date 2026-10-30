from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from agentlink_runtime.aip_client_util import aip_start_structured
from agentlink_runtime.aip_payload import wrap_business
from agentlink_runtime.audit import AuditLog
from agentlink_runtime.authz import AuthzLevel
from commerce.env_loader import load_dotenv

load_dotenv()

from agentlink_runtime.gateway import AgentContext, ToolGateway, ToolSpec
from agentlink_runtime.graph_base import new_state
from agentlink_runtime.memory import MemoryStore
from agents.buyer_a.graph import (
    build_order_draft,
    build_quote_request,
    compare_quotes,
    run_buyer_plan,
)

ROOT = Path(__file__).resolve().parent
POLICY = yaml.safe_load((ROOT / "policy.yaml").read_text(encoding="utf-8"))

AIC = os.getenv("BUYER_A_AIC", "buyer-a-local-aic")
AGENT_ID = "buyer-a"
TENANT_ID = "buyer-org-a"
SUPPLIER_RPC = os.getenv("SUPPLIER_A_RPC_URL", "http://127.0.0.1:8011/rpc")
LOGISTICS_RPC = os.getenv("LOGISTICS_RPC_URL", "http://127.0.0.1:8015/rpc")

app = FastAPI(title="采购商A", version="0.3.0")
audit = AuditLog(Path("logs") / "buyer_a_audit.jsonl")
gateway = ToolGateway(audit=audit)
memory = MemoryStore(agent_id=AGENT_ID, tenant_id=TENANT_ID)
_store: dict[str, dict[str, Any]] = {}

# 座椅商城 + ERP 业务 API
os.environ.setdefault("BUYER_AGENT_ID", "buyer-a")

os.environ.setdefault("AGENTLINK_RUNTIME", "v2")

from commerce.buyer_routes import mount_buyer_commerce  # noqa: E402
from commerce.seed import seed_buyer_a  # noqa: E402
from commerce_v2.runtime_flag import use_v2  # noqa: E402

try:
    seed_buyer_a(reset=False)
except Exception:
    seed_buyer_a(reset=True)
mount_buyer_commerce(app, aic=AIC, agent_id=AGENT_ID)
# 旧采购案流仅在 legacy 运行时挂载；v2 用 /api/flow/cases（commerce_v2）
if not use_v2():
    from commerce.flow_routes import mount_procurement_flow  # noqa: E402

    mount_procurement_flow(app)


@app.on_event("startup")
def _start_amp_heartbeat() -> None:
    try:
        from commerce.amp_log import start_heartbeat

        start_heartbeat(aic=AIC, agent_id=AGENT_ID)
    except Exception:  # noqa: BLE001
        pass


class PurchaseCreate(BaseModel):
    product_name: str = "重型脚轮"
    rated_load_kg_min: int = 300
    quantity: int = 500
    currency: str = "CNY"
    max_total_cost: float = 25000
    deadline: str = "2026-10-30"
    approve: bool = True


class RfqRequest(BaseModel):
    business_id: str
    partner_url: str = Field(default_factory=lambda: SUPPLIER_RPC)
    supplier_aic: str = Field(
        default_factory=lambda: os.getenv("SUPPLIER_A_AIC", "supplier-a-local-aic")
    )


class PartnerRef(BaseModel):
    partner_url: str
    supplier_aic: str


class RfqMultiRequest(BaseModel):
    business_id: str
    partners: list[PartnerRef]


class ShippingRequest(BaseModel):
    business_id: str
    partner_url: str = Field(default_factory=lambda: LOGISTICS_RPC)
    logistics_aic: str = Field(
        default_factory=lambda: os.getenv("LOGISTICS_AIC", "logistics-local-aic")
    )
    weight_kg: float = 200.0
    postal_code: str = "310000"
    zone: str = "domestic"


def _pr_from_body(body: PurchaseCreate) -> dict[str, Any]:
    return {
        "purchase_request_id": f"pr-{uuid4().hex[:8]}",
        "version": 1,
        "product_category": "industrial_caster",
        "product_name": body.product_name,
        "specifications": {"rated_load_kg_min": body.rated_load_kg_min},
        "quantity": body.quantity,
        "currency": body.currency,
        "budget": {
            "max_total_cost": body.max_total_cost,
            "cost_basis": "landed_cost",
            "tax_included": True,
        },
        "quality_requirements": ["提供批次质检资料"],
        "delivery": {"deadline": body.deadline, "destination_ref": "addr-buyer-1"},
        "hard_constraints": POLICY.get("hard_constraints", []),
        "human_approval_status": "approved" if body.approve else "draft",
    }


async def _tool_send_rfq(arguments: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    business_id = arguments["business_id"]
    rec = _store.get(business_id)
    if not rec:
        raise ValueError("business not found")
    pr = rec["purchase_request"]
    if pr.get("human_approval_status") != "approved":
        raise PermissionError("PR_NOT_APPROVED")

    deadline = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    envelope = build_quote_request(
        business_id=business_id,
        purchase_request=pr,
        quote_deadline=deadline,
    )
    assert "budget" not in envelope["payload"]

    supplier_aic = arguments.get("supplier_aic") or os.getenv(
        "SUPPLIER_A_AIC", "supplier-a-local-aic"
    )
    session_id = f"rfq-{business_id}-{supplier_aic}"
    result = await aip_start_structured(
        partner_url=arguments["partner_url"],
        leader_aic=AIC,
        partner_aic=supplier_aic,
        session_id=session_id,
        envelope=envelope,
        local_agent_id=AGENT_ID,
    )
    rec.setdefault("quotes", [])
    if result.get("envelope"):
        rec["quotes"].append(result["envelope"])
    rec["last_task"] = {
        "task_id": result["task_id"],
        "state": result["state"],
        "session_id": session_id,
    }
    return {
        "task_id": result["task_id"],
        "state": result["state"],
        "quote": result.get("envelope"),
        "session_id": session_id,
        "message": result.get("message"),
    }


async def _tool_send_rfq_multi(arguments: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    results = []
    for partner in arguments.get("partners") or []:
        one = await _tool_send_rfq(
            {
                "business_id": arguments["business_id"],
                "partner_url": partner["partner_url"],
                "supplier_aic": partner["supplier_aic"],
            },
            ctx,
        )
        results.append(one)
    return {"results": results, "quote_count": sum(1 for r in results if r.get("quote"))}


async def _tool_request_shipping(arguments: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    business_id = arguments["business_id"]
    rec = _store.get(business_id)
    if not rec:
        raise ValueError("business not found")
    ship_env = wrap_business(
        "agentlink.shipping_request",
        business_id,
        {
            "weight_kg": arguments["weight_kg"],
            "zone": arguments.get("zone", "domestic"),
            "destination": {"postal_code": arguments["postal_code"]},
        },
    )
    session_id = f"ship-{business_id}"
    result = await aip_start_structured(
        partner_url=arguments["partner_url"],
        leader_aic=AIC,
        partner_aic=arguments.get("logistics_aic") or "logistics-local-aic",
        session_id=session_id,
        envelope=ship_env,
        local_agent_id=AGENT_ID,
    )
    if result.get("envelope"):
        rec["shipping_quote"] = result["envelope"]
        # 合入比较视图（不把供应商原文给物流；此处仅存运费）
        comparison = compare_quotes(rec.get("quotes") or [])
        ship_cost = (result["envelope"].get("payload") or {}).get("shipping_cost")
        for row in comparison.get("quotes") or []:
            row["shipping_cost"] = ship_cost
            row["shipping_unknown"] = ship_cost is None
            if row.get("unit_price") is not None and ship_cost is not None:
                qty = int((rec["purchase_request"] or {}).get("quantity") or 0)
                row["tco_estimate"] = round(float(row["unit_price"]) * qty + float(ship_cost), 2)
        rec["comparison"] = comparison
    return {
        "task_id": result["task_id"],
        "state": result["state"],
        "shipping_quote": result.get("envelope"),
        "session_id": session_id,
        "message": result.get("message"),
    }


async def _tool_compare(arguments: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    business_id = arguments["business_id"]
    rec = _store.get(business_id)
    if not rec:
        raise ValueError("business not found")
    comparison = compare_quotes(rec.get("quotes") or [])
    ship = ((rec.get("shipping_quote") or {}).get("payload") or {})
    ship_cost = ship.get("shipping_cost")
    if ship_cost is not None:
        qty = int((rec.get("purchase_request") or {}).get("quantity") or 0)
        for row in comparison.get("quotes") or []:
            row["shipping_cost"] = ship_cost
            row["shipping_unknown"] = False
            if row.get("unit_price") is not None:
                row["tco_estimate"] = round(float(row["unit_price"]) * qty + float(ship_cost), 2)
    rec["comparison"] = comparison
    return comparison


async def _tool_create_order_draft(arguments: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    business_id = arguments["business_id"]
    rec = _store.get(business_id)
    if not rec:
        raise ValueError("business not found")
    quotes = rec.get("quotes") or []
    if not quotes:
        raise ValueError("no quotes to draft from")
    # 默认取比较后最优；若无比较则取第一份
    comparison = rec.get("comparison") or compare_quotes(quotes)
    rec["comparison"] = comparison
    best_id = (comparison.get("quotes") or [{}])[0].get("quote_id")
    selected = next(
        (q for q in quotes if (q.get("payload") or q).get("quote_id") == best_id),
        quotes[0],
    )
    draft = build_order_draft(
        business_id=business_id,
        purchase_request=rec["purchase_request"],
        selected_quote=selected,
    )
    rec["order_draft"] = draft
    return draft


async def _tool_activate_order(arguments: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    # 本地策略默认关闭；即便注册成功也要求 commit+HITL
    if not POLICY.get("allow_activate_order", False):
        raise PermissionError("ACTIVATE_DISABLED_BY_POLICY")
    raise PermissionError("ACTIVATE_REQUIRES_HITL")


gateway.register(
    ToolSpec(
        name="send_rfq",
        authz_min=AuthzLevel.NEGOTIATE,
        handler=_tool_send_rfq,
        side_effects="aip_out",
        description="向供应商发起 RFQ。仅在采购需求已批准后使用；禁止把预算字段发出去。",
    )
)
gateway.register(
    ToolSpec(
        name="send_rfq_multi",
        authz_min=AuthzLevel.NEGOTIATE,
        handler=_tool_send_rfq_multi,
        side_effects="aip_out",
        description="并行向多家供应商发起 RFQ。",
    )
)
gateway.register(
    ToolSpec(
        name="request_shipping",
        authz_min=AuthzLevel.NEGOTIATE,
        handler=_tool_request_shipping,
        side_effects="aip_out",
        description="向物流 Agent 询运费并合入 TCO 估算。",
    )
)
gateway.register(
    ToolSpec(
        name="compare_quotes",
        authz_min=AuthzLevel.SUGGEST,
        handler=_tool_compare,
        side_effects="none",
        description="比较已收集报价；运费 null 视为未知而非 0。",
    )
)
gateway.register(
    ToolSpec(
        name="create_order_draft",
        authz_min=AuthzLevel.NEGOTIATE,
        handler=_tool_create_order_draft,
        side_effects="db_write",
        description="根据最优报价生成订单草案，不激活成交。",
    )
)
gateway.register(
    ToolSpec(
        name="activate_order",
        authz_min=AuthzLevel.COMMIT,
        handler=_tool_activate_order,
        human_confirm=True,
        side_effects="irreversible",
        description="激活订单（critical）。本地默认禁用；生产需 commit + HITL。",
    )
)


@app.get("/")
async def root() -> RedirectResponse:
    """浏览器打开 :8010 时跳到采购控制台 UI（默认 :8090）。"""
    target = os.getenv("AGENTLINK_UI_PUBLIC_URL", "https://ashui.online:8090/")
    return RedirectResponse(url=target, status_code=302)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "aic": AIC, "agent_id": AGENT_ID, "tools": gateway.list_catalog()}


@app.post("/api/purchases")
async def create_purchase(body: PurchaseCreate) -> dict[str, Any]:
    pr = _pr_from_body(body)
    business_id = f"purchase-{uuid4().hex[:8]}"
    state = new_state(
        agent_id=AGENT_ID,
        aic=AIC,
        tenant_id=TENANT_ID,
        business_id=business_id,
        session_id=f"session-{business_id}",
        authz_level=str(POLICY.get("authz_level", "negotiate")),
    )
    state = run_buyer_plan(state, pr)
    if state.get("error"):
        raise HTTPException(status_code=400, detail=state.get("outcome"))
    _store[business_id] = {
        "purchase_request": pr,
        "quotes": [],
        "state": state,
    }
    memory.set_working(business_id, pr)
    memory.append_event({"type": "pr_created", "business_id": business_id})
    return {"business_id": business_id, "purchase_request": pr}


def _ctx(business_id: str, level: AuthzLevel | None = None) -> AgentContext:
    return AgentContext(
        agent_id=AGENT_ID,
        aic=AIC,
        tenant_id=TENANT_ID,
        authz_level=level or AuthzLevel(POLICY.get("authz_level", "negotiate")),
        business_id=business_id,
    )


@app.post("/api/purchases/{business_id}/rfq")
async def send_rfq(business_id: str, body: RfqRequest | None = None) -> dict[str, Any]:
    body = body or RfqRequest(business_id=business_id)
    if body.business_id != business_id:
        raise HTTPException(status_code=400, detail="business_id mismatch")
    if business_id not in _store:
        raise HTTPException(status_code=404, detail="business not found")
    result = await gateway.execute(
        _ctx(business_id),
        "send_rfq",
        {
            "business_id": business_id,
            "partner_url": body.partner_url,
            "supplier_aic": body.supplier_aic,
        },
        idempotency_key=f"rfq:{business_id}:{body.supplier_aic}:{_store[business_id]['purchase_request']['version']}",
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail={"status": result.status, "error": result.error})
    return result.data


@app.post("/api/purchases/{business_id}/rfq-multi")
async def send_rfq_multi(business_id: str, body: RfqMultiRequest) -> dict[str, Any]:
    if body.business_id != business_id:
        raise HTTPException(status_code=400, detail="business_id mismatch")
    if business_id not in _store:
        raise HTTPException(status_code=404, detail="business not found")
    result = await gateway.execute(
        _ctx(business_id),
        "send_rfq_multi",
        {
            "business_id": business_id,
            "partners": [p.model_dump() for p in body.partners],
        },
        idempotency_key=f"rfq-multi:{business_id}:{len(body.partners)}",
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail={"status": result.status, "error": result.error})
    return result.data


@app.post("/api/purchases/{business_id}/shipping")
async def request_shipping(business_id: str, body: ShippingRequest) -> dict[str, Any]:
    if body.business_id != business_id:
        raise HTTPException(status_code=400, detail="business_id mismatch")
    if business_id not in _store:
        raise HTTPException(status_code=404, detail="business not found")
    result = await gateway.execute(
        _ctx(business_id),
        "request_shipping",
        body.model_dump(),
        idempotency_key=f"ship:{business_id}:{body.postal_code}:{body.weight_kg}",
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail={"status": result.status, "error": result.error})
    return result.data


@app.get("/api/purchases/{business_id}/comparison")
async def get_comparison(business_id: str) -> dict[str, Any]:
    ctx = AgentContext(
        agent_id=AGENT_ID,
        aic=AIC,
        tenant_id=TENANT_ID,
        authz_level=AuthzLevel.SUGGEST,
        business_id=business_id,
    )
    result = await gateway.execute(ctx, "compare_quotes", {"business_id": business_id})
    if not result.ok:
        raise HTTPException(status_code=400, detail={"status": result.status, "error": result.error})
    return result.data


@app.post("/api/purchases/{business_id}/order-draft")
async def create_draft(business_id: str) -> dict[str, Any]:
    if business_id not in _store:
        raise HTTPException(status_code=404, detail="business not found")
    ctx = AgentContext(
        agent_id=AGENT_ID,
        aic=AIC,
        tenant_id=TENANT_ID,
        authz_level=AuthzLevel(POLICY.get("authz_level", "negotiate")),
        business_id=business_id,
    )
    result = await gateway.execute(
        ctx,
        "create_order_draft",
        {"business_id": business_id},
        idempotency_key=f"draft:{business_id}",
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail={"status": result.status, "error": result.error})
    return result.data


@app.post("/api/purchases/{business_id}/activate")
async def activate(business_id: str) -> dict[str, Any]:
    """本地应返回 400：权限不足或策略禁用（验证护栏）。"""
    if business_id not in _store:
        raise HTTPException(status_code=404, detail="business not found")
    ctx = AgentContext(
        agent_id=AGENT_ID,
        aic=AIC,
        tenant_id=TENANT_ID,
        authz_level=AuthzLevel(POLICY.get("authz_level", "negotiate")),
        business_id=business_id,
    )
    result = await gateway.execute(ctx, "activate_order", {"business_id": business_id})
    if not result.ok:
        raise HTTPException(status_code=400, detail={"status": result.status, "error": result.error})
    return result.data


@app.get("/api/purchases/{business_id}/audit")
async def get_audit(business_id: str) -> dict[str, Any]:
    events = [e.__dict__ for e in audit.by_business(business_id)]
    return {"business_id": business_id, "events": events}


def main() -> None:
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8010"))
    uvicorn.run("agents.buyer_a.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
