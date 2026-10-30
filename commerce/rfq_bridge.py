"""缺口 → 按 preferred_supplier 向对应 Agent 发 AIP RFQ。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_client_util import aip_start_structured
from agentlink_runtime.aip_payload import wrap_business
from commerce import supplier_service as ss

SUPPLIER_MAP = {
    "supplier-a": {
        "url": os.getenv("SUPPLIER_A_RPC_URL", "http://127.0.0.1:8011/rpc"),
        "aic": os.getenv("SUPPLIER_A_AIC", "supplier-a-local-aic"),
        "agent_id": "supplier-a",
    },
    "supplier-b": {
        "url": os.getenv("SUPPLIER_B_RPC_URL", "http://127.0.0.1:8013/rpc"),
        "aic": os.getenv("SUPPLIER_B_AIC", "supplier-b-local-aic"),
        "agent_id": "supplier-b",
    },
    "supplier-c": {
        "url": os.getenv("SUPPLIER_C_RPC_URL", "http://127.0.0.1:8014/rpc"),
        "aic": os.getenv("SUPPLIER_C_AIC", "supplier-c-local-aic"),
        "agent_id": "supplier-c",
    },
}
# 云上部署时 remote_install 会把上述 URL 写成 https://公网IP:port/rpc


async def rfq_shortages(
    shortages: list[dict[str, Any]],
    *,
    leader_aic: str,
    local_agent_id: str = "buyer-a",
) -> dict[str, Any]:
    business_id = f"replenish-{uuid4().hex[:8]}"
    results = []
    errors = []
    # 按供应商聚合
    groups: dict[str, list[dict[str, Any]]] = {}
    for s in shortages:
        pref = s.get("preferred_supplier") or "supplier-a"
        groups.setdefault(pref, []).append(s)

    for pref, items in groups.items():
        meta = SUPPLIER_MAP.get(pref)
        if not meta:
            errors.append(f"未知供应商 {pref}")
            continue
        for item in items:
            qty = max(float(item.get("short_vs_safety") or item.get("need") or 1), 1)
            # 面料定制字段；供应商B有MOQ=200
            specs: dict[str, Any] = {"material_code": item["material_code"]}
            if item["material_code"] == "RM-FABRIC-BLK":
                specs.update({"material": "fabric", "color": "black"})
                qty = max(qty, 200)
            envelope = wrap_business(
                "agentlink.quote_request",
                business_id,
                {
                    "purchase_request_id": f"pr-{uuid4().hex[:8]}",
                    "version": 1,
                    "product_name": item.get("name") or item["material_code"],
                    "specifications": specs,
                    "quantity": int(qty) if qty >= 1 else 1,
                    "currency": "CNY",
                    "tax_included_required": True,
                    "quote_deadline": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
                },
            )
            try:
                out = await aip_start_structured(
                    partner_url=meta["url"],
                    leader_aic=leader_aic,
                    partner_aic=meta["aic"],
                    session_id=f"rfq-{business_id}-{item['material_code']}",
                    envelope=envelope,
                    local_agent_id=local_agent_id,
                )
                ss.record_rfq(
                    meta["agent_id"],
                    business_id=business_id,
                    buyer_ref=local_agent_id,
                    material_code=item["material_code"],
                    qty=qty,
                    request=envelope,
                    response=out.get("envelope"),
                    status=out.get("state") or "unknown",
                )
                results.append(
                    {
                        "supplier": pref,
                        "material_code": item["material_code"],
                        "state": out.get("state"),
                        "quote": out.get("envelope"),
                        "message": out.get("message"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{pref}/{item['material_code']}: {exc}")

    return {
        "business_id": business_id,
        "results": results,
        "quote_count": sum(1 for r in results if r.get("quote")),
        "errors": errors,
    }
