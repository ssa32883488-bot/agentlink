"""Leader 侧 AIP 调用工具。"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from acps_sdk.aip import AipRpcClient, TaskCommand, TaskCommandType, TaskResult

from agentlink_runtime.aip_payload import as_structured_item, extract_structured
from agentlink_runtime.interactions import log_interaction
from agentlink_runtime.mtls import build_client_ssl_context


async def aip_start_structured(
    *,
    partner_url: str,
    leader_aic: str,
    partner_aic: str,
    session_id: str,
    envelope: dict[str, Any],
    local_agent_id: str | None = None,
) -> dict[str, Any]:
    client = AipRpcClient(
        partner_url=partner_url,
        leader_id=leader_aic,
        expected_partner_aic=partner_aic,
        identity_binding_enabled=os.getenv("AIP_IDENTITY_BINDING", "0") == "1",
        ssl_context=build_client_ssl_context(),
    )
    task_id = f"task-{uuid4().hex[:12]}"
    try:
        command = TaskCommand(
            id=f"cmd-{uuid4()}",
            sentAt=datetime.now(timezone.utc).isoformat(),
            senderRole="leader",
            senderId=leader_aic,
            dataItems=[as_structured_item(envelope)],
            sessionId=session_id,
            command=TaskCommandType.Start,
            taskId=task_id,
        )
        response = await client._send_request(command)
        if not isinstance(response.result, TaskResult):
            raise TypeError(f"Expected TaskResult, got {type(response.result)}")
        task = response.result
        product_env = None
        if task.products:
            for product in task.products:
                product_env = extract_structured(product.dataItems)
                if product_env:
                    break
        state_val = task.status.state.value if hasattr(task.status.state, "value") else str(task.status.state)
        out = {
            "task_id": task.taskId,
            "state": state_val,
            "envelope": product_env,
            "session_id": session_id,
            "message": None if product_env else _first_text(task),
        }
        log_interaction(
            {
                "direction": "outbound",
                "local_agent_id": local_agent_id or "leader",
                "from_aic": leader_aic,
                "to_aic": partner_aic,
                "to_url": partner_url,
                "session_id": session_id,
                "task_id": task.taskId,
                "state": state_val,
                "business_id": envelope.get("business_id"),
                "req_schema": envelope.get("schema_type"),
                "res_schema": (product_env or {}).get("schema_type") if product_env else None,
                "request": envelope,
                "response": product_env,
                "message": out.get("message"),
            }
        )
        try:
            from commerce.amp_log import record_access

            record_access(
                task_id=task.taskId or task_id,
                local_aic=leader_aic,
                peer_aic=partner_aic,
                direction="send",
                endpoint=partner_url,
                status=state_val,
                extra={"schema": envelope.get("schema_type"), "business_id": envelope.get("business_id")},
            )
        except Exception:  # noqa: BLE001
            pass
        return out
    finally:
        await client.close()


def _first_text(task: TaskResult) -> str | None:
    from agentlink_runtime.aip_payload import extract_text

    if task.products:
        for p in task.products:
            t = extract_text(p.dataItems)
            if t:
                return t
    # Java / AIP reject reasons are often on status.dataItems (type=text)
    status = getattr(task, "status", None)
    if status is not None:
        t = extract_text(getattr(status, "dataItems", None))
        if t:
            return t
    return None
