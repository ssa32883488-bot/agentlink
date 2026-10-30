from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agentlink_runtime.aip_client_util import aip_start_structured
from agentlink_runtime.audit import AuditLog
from agentlink_runtime.authz import AuthzLevel
from agentlink_runtime.gateway import AgentContext, ToolGateway, ToolSpec
from agentlink_runtime.graph_base import new_state
from agentlink_runtime.memory import MemoryStore
from agents.buyer_b.graph import (
    build_order_draft,
    build_quote_request,
    check_quick_reorder_policy,
    compare_quotes,
    run_buyer_plan,
)

ROOT = Path(__file__).resolve().parent
POLICY = yaml.safe_load((ROOT / "policy.yaml").read_text(encoding="utf-8"))

os.environ.setdefault("BUYER_AGENT_ID", "buyer-b")

AIC = os.getenv("BUYER_B_AIC", "buyer-b-local-aic")
AGENT_ID = "buyer-b"
TENANT_ID = "buyer-org-b"
SUPPLIER_RPC = os.getenv("SUPPLIER_A_RPC_URL", "http://127.0.0.1:8011/rpc")

app = FastAPI(title="AgentLink Buyer B", version="0.2.0")
audit = AuditLog(Path("logs") / "buyer_b_audit.jsonl")
gateway = ToolGateway(audit=audit)
memory = MemoryStore(agent_id=AGENT_ID, tenant_id=TENANT_ID)
_store: dict[str, dict[str, Any]] = {}

# 与采购商A同构：独立库 + ERP 对话 + 采购案流
os.environ.setdefault("AGENTLINK_RUNTIME", "v2")

from commerce.buyer_routes import mount_buyer_commerce  # noqa: E402
from commerce.seed import seed_buyer_b  # noqa: E402
from commerce_v2.runtime_flag import use_v2  # noqa: E402

try:
    seed_buyer_b(reset=False)
except Exception:
    seed_buyer_b(reset=True)
mount_buyer_commerce(app, aic=AIC, agent_id=AGENT_ID)
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
    quantity: int = 100
    currency: str = "CNY"
    max_total_cost: float = 5000
    deadline: str = "2026-10-30"
    approve: bool = True


class RfqRequest(BaseModel):
    business_id: str
    partner_url: str = Field(default_factory=lambda: SUPPLIER_RPC)
    supplier_aic: str = "supplier-a-local-aic"


def _pr_from_body(body: PurchaseCreate) -> dict[str, Any]:
    return {
        "purchase_request_id": f"pr-b-{uuid4().hex[:8]}",
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
        "delivery": {"deadline": body.deadline, "destination_ref": "addr-buyer-b"},
        "hard_constraints": POLICY.get("hard_constraints", []),
        "human_approval_status": "approved" if body.approve else "draft",
        "mode": "quick_reorder",
    }


async def _tool_send_rfq(arguments: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    business_id = arguments["business_id"]
    rec = _store.get(business_id)
    if not rec:
        raise ValueError("business not found")
    pr = rec["purchase_request"]
    if pr.get("human_approval_status") != "approved":
        raise PermissionError("PR_NOT_APPROVED")

    supplier_aic = arguments.get("supplier_aic") or "supplier-a-local-aic"
    reason = check_quick_reorder_policy(POLICY, pr, supplier_aic)
    if reason:
        raise PermissionError(f"QUICK_REORDER_BLOCKED: {reason}")

    deadline = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    envelope = build_quote_request(
        business_id=business_id,
        purchase_request=pr,
        quote_deadline=deadline,
    )
    assert "budget" not in envelope["payload"]
    session_id = f"rfq-b-{business_id}-{supplier_aic}"
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
    return {
        "task_id": result["task_id"],
        "state": result["state"],
        "quote": result.get("envelope"),
        "session_id": session_id,
    }


async def _tool_create_order_draft(arguments: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    business_id = arguments["business_id"]
    rec = _store.get(business_id)
    if not rec:
        raise ValueError("business not found")
    quotes = rec.get("quotes") or []
    if not quotes:
        raise ValueError("no quotes")
    draft = build_order_draft(
        business_id=business_id,
        purchase_request=rec["purchase_request"],
        selected_quote=quotes[0],
    )
    rec["order_draft"] = draft
    return draft


gateway.register(
    ToolSpec(
        name="send_rfq",
        authz_min=AuthzLevel.NEGOTIATE,
        handler=_tool_send_rfq,
        side_effects="aip_out",
        description="快速复购单源 RFQ；白名单与限额由 Policy 硬校验。",
    )
)
gateway.register(
    ToolSpec(
        name="create_order_draft",
        authz_min=AuthzLevel.NEGOTIATE,
        handler=_tool_create_order_draft,
        side_effects="db_write",
        description="生成订单草案。",
    )
)


@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse

    target = os.getenv("AGENTLINK_UI_PUBLIC_URL", "https://ashui.online:8092/")
    return RedirectResponse(url=target, status_code=302)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "aic": AIC, "agent_id": AGENT_ID, "tools": gateway.list_catalog()}


@app.post("/api/purchases")
async def create_purchase(body: PurchaseCreate) -> dict[str, Any]:
    pr = _pr_from_body(body)
    # 限额闸：创建时即校验
    if float(pr["budget"]["max_total_cost"]) > float(POLICY.get("max_total_cost", 0)):
        raise HTTPException(
            status_code=400,
            detail={
                "status": "OVER_LIMIT",
                "error": f"escalate_to_buyer_a: budget>{POLICY.get('max_total_cost')}",
            },
        )
    business_id = f"purchase-b-{uuid4().hex[:8]}"
    state = run_buyer_plan(
        new_state(
            agent_id=AGENT_ID,
            aic=AIC,
            tenant_id=TENANT_ID,
            business_id=business_id,
            session_id=f"session-{business_id}",
            authz_level=str(POLICY.get("authz_level", "negotiate")),
        ),
        pr,
    )
    if state.get("error"):
        raise HTTPException(status_code=400, detail=state.get("outcome"))
    _store[business_id] = {"purchase_request": pr, "quotes": [], "state": state}
    memory.set_working(business_id, pr)
    return {"business_id": business_id, "purchase_request": pr}


@app.post("/api/purchases/{business_id}/rfq")
async def send_rfq(business_id: str, body: RfqRequest) -> dict[str, Any]:
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
        "send_rfq",
        body.model_dump(),
        idempotency_key=f"rfq:{business_id}:{body.supplier_aic}",
    )
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
    result = await gateway.execute(ctx, "create_order_draft", {"business_id": business_id})
    if not result.ok:
        raise HTTPException(status_code=400, detail={"status": result.status, "error": result.error})
    return result.data


@app.get("/api/purchases/{business_id}/audit")
async def get_audit(business_id: str) -> dict[str, Any]:
    return {"business_id": business_id, "events": [e.__dict__ for e in audit.by_business(business_id)]}


def main() -> None:
    import uvicorn

    uvicorn.run(
        "agents.buyer_b.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8012")),
        reload=False,
    )


if __name__ == "__main__":
    main()
