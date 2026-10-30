"""采购 V1 Tools · Pydantic 入参/出参（与 design_buyer_tools_schema_v1.md 对齐）。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PartnerRef(BaseModel):
    agent_id: str | None = None
    aic: str
    name: str | None = None
    endpoint: str
    skills: list[str] = Field(default_factory=list)


class LineItem(BaseModel):
    sku: str
    name: str | None = None
    qty: float = 1
    unit: str = "件"
    specs: dict[str, Any] = Field(default_factory=dict)


class FreightQuote(BaseModel):
    amount: float = 0
    currency: str = "CNY"
    note: str | None = None


class DiscoverIn(BaseModel):
    case_id: str | None = None
    query: str = ""
    limit: int = Field(5, ge=1, le=10)
    refresh: bool = False
    # 默认留空，由调用方传入本窗主体；禁止静默当成脚轮
    product_name: str = ""
    quantity: int = Field(500, ge=1)
    rated_load_kg_min: int = 300
    # 组合需求行项目；有多行时先统一发现/短名单，询价后再建议拆单
    lines: list[LineItem] = Field(default_factory=list)


class CandidateOut(BaseModel):
    candidate_id: str
    agent_id: str | None = None
    aic: str
    name: str
    endpoint: str
    skills: list[str] = Field(default_factory=list)
    matched_skill: str | None = None
    match_reason: str = ""
    source_label: str = "平台发现"
    trade_name: str | None = None
    address: str | None = None
    city: str | None = None
    business: str | None = None


class UiHintShortlist(BaseModel):
    form: Literal["shortlist_confirm"] = "shortlist_confirm"
    title: str = "请确认询价短名单"
    min_select: int = 1
    max_select: int = 5
    submit_action: str = "rfq.send_batch"


class DiscoverOut(BaseModel):
    ok: bool = True
    case_id: str
    source: str
    discovery_url: str | None = None
    elapsed_ms: int | None = None
    platform_error: str | None = None
    candidates: list[CandidateOut] = Field(default_factory=list)
    ui_hint: UiHintShortlist | None = None
    hitl: dict[str, Any] | None = None
    error: dict[str, str] | None = None


class RfqBatchIn(BaseModel):
    case_id: str | None = None
    selected: list[str | dict[str, Any]] = Field(..., min_length=1, max_length=5)
    timeout_ms: int = 60000


class QuoteRow(BaseModel):
    partner: PartnerRef
    status: Literal["ok", "timeout", "error", "rejected"] = "ok"
    error: str | None = None
    task_id: str | None = None
    distance_km: float | None = None
    lead_time_days: float | None = None
    line_prices: list[dict[str, Any]] = Field(default_factory=list)
    goods_total: float | None = None
    freight: FreightQuote | None = None
    grand_total: float | None = None
    currency: str = "CNY"
    raw_policy_hints: list[str] = Field(default_factory=list)


class RfqBatchOut(BaseModel):
    ok: bool = True
    case_id: str
    parallel: int = 0
    quotes: list[QuoteRow] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    ui_hint: dict[str, Any] | None = None
    hitl: dict[str, Any] | None = None
    error: dict[str, str] | None = None


class PartnerDialogIn(BaseModel):
    case_id: str | None = None
    partner: str | dict[str, Any]
    intent: Literal["negotiate", "clarify", "requote", "initial_quote"] = "negotiate"
    goal_text: str = "保质保交期前提下优化总价"
    message: str = ""
    timeout_ms: int = 60000


class PartnerDialogOut(BaseModel):
    ok: bool = True
    case_id: str
    partner: PartnerRef | None = None
    intent: str
    task_id: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, str] | None = None


class MemoryInjectIn(BaseModel):
    case_id: str | None = None
    entries: list[dict[str, Any]] = Field(default_factory=list)


class MemoryExtractIn(BaseModel):
    case_id: str | None = None
    keys: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class MemoryRecordIn(BaseModel):
    case_id: str | None = None
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ref_ids: list[str] = Field(default_factory=list)
