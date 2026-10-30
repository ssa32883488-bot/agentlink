"""采购 10 步流程 HTTP API（挂到采购商A）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from commerce import flow_service as fs
from commerce import procurement_case as pc

router = APIRouter(tags=["procurement-flow"])


class BriefIn(BaseModel):
    product_name: str = "重型脚轮"
    quantity: int = Field(500, ge=1)
    rated_load_kg_min: int = 300
    note: str = ""


class DiscoverIn(BaseModel):
    query: str | None = None
    refresh: bool = Field(False, description="True=绕过发现缓存，强制打梧桐 ADP（演示/验收用）")


class ShortlistIn(BaseModel):
    agent_ids: list[str] = Field(..., min_length=1)


class DecideIn(BaseModel):
    action: str = Field(..., description="order | negotiate | auction")
    supplier_agent_id: str | None = None
    goal: str | None = None
    sku: str | None = Field(None, description="组合需求下单时指定本单物料 SKU，禁止用多行数量加总")


class ShippingIn(BaseModel):
    weight_kg: float = 200.0
    postal_code: str = "310000"


class HitlDecideIn(BaseModel):
    decision: str = Field(..., description="approve | edit | reject | respond")
    agent_ids: list[str] = Field(default_factory=list)
    note: str = ""


def mount_procurement_flow(app) -> None:
    @router.get("/api/flow/cases")
    def list_cases() -> dict[str, Any]:
        return {"items": pc.list_cases()}

    @router.post("/api/flow/cases")
    def create_case(body: BriefIn) -> dict[str, Any]:
        return fs.create_from_brief(
            product_name=body.product_name,
            quantity=body.quantity,
            rated_load_kg_min=body.rated_load_kg_min,
            note=body.note,
        )

    @router.get("/api/flow/cases/{case_id}")
    def get_case(case_id: str) -> dict[str, Any]:
        case = pc.get_case(case_id)
        if not case:
            raise HTTPException(404, "case not found")
        return case

    @router.post("/api/flow/cases/{case_id}/discover")
    async def discover(case_id: str, body: DiscoverIn | None = None) -> dict[str, Any]:
        try:
            return await fs.step_discover(
                case_id,
                (body.query if body else None),
                bypass_cache=bool(body.refresh) if body else False,
            )
        except KeyError:
            raise HTTPException(404, "case not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/confirm-shortlist")
    def confirm_shortlist(case_id: str, body: ShortlistIn) -> dict[str, Any]:
        try:
            return fs.step_confirm_shortlist(case_id, body.agent_ids)
        except KeyError:
            raise HTTPException(404, "case not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/hitl")
    def hitl_decide(case_id: str, body: HitlDecideIn) -> dict[str, Any]:
        try:
            return fs.step_hitl_decide(
                case_id,
                body.decision,
                agent_ids=body.agent_ids or None,
                note=body.note or "",
            )
        except KeyError:
            raise HTTPException(404, "case not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.get("/api/flow/metrics")
    def flow_metrics() -> dict[str, Any]:
        """应用成效只读看板数据（AMP 本地日志汇总，不改协议）。"""
        from commerce.amp_metrics import summarize_amp

        return summarize_amp()

    @router.post("/api/flow/cases/{case_id}/rfq")
    async def rfq(case_id: str) -> dict[str, Any]:
        try:
            return await fs.step_rfq(case_id)
        except KeyError:
            raise HTTPException(404, "case not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/decide")
    def decide(case_id: str, body: DecideIn) -> dict[str, Any]:
        try:
            return fs.step_decide(
                case_id,
                body.action,
                supplier_agent_id=body.supplier_agent_id,
                goal=body.goal,
                sku=body.sku,
            )
        except KeyError:
            raise HTTPException(404, "case not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/negotiate")
    async def negotiate(case_id: str) -> dict[str, Any]:
        try:
            return await fs.step_negotiate(case_id)
        except KeyError:
            raise HTTPException(404, "case not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/auction")
    async def auction(case_id: str) -> dict[str, Any]:
        try:
            return await fs.step_auction(case_id)
        except KeyError:
            raise HTTPException(404, "case not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/shipping")
    async def shipping(case_id: str, body: ShippingIn | None = None) -> dict[str, Any]:
        body = body or ShippingIn()
        try:
            return await fs.step_shipping(case_id, weight_kg=body.weight_kg, postal_code=body.postal_code)
        except KeyError:
            raise HTTPException(404, "case not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/confirm-buyer")
    def confirm_buyer(case_id: str) -> dict[str, Any]:
        try:
            return fs.step_buyer_confirm(case_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/confirm-supplier")
    async def confirm_supplier(case_id: str) -> dict[str, Any]:
        try:
            return await fs.step_supplier_confirm(case_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/flow/cases/{case_id}/activate")
    def activate(case_id: str) -> dict[str, Any]:
        try:
            return fs.step_activate(case_id)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    app.include_router(router)
