"""AIP Partner 进程脚手架：供应商 / 物流共用。"""
from __future__ import annotations

import inspect
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from acps_sdk.aip import Product, TaskCommand, TaskResult, TaskState, TextDataItem
from acps_sdk.aip.aip_peer_cert import AipPeerCertificateMiddleware
from acps_sdk.aip.aip_rpc_server import (
    CommandHandlers,
    DefaultHandlers,
    TaskManager,
    add_aip_rpc_router,
)
from fastapi import FastAPI

from agentlink_runtime.aip_payload import as_structured_item, extract_structured
from agentlink_runtime.graph_base import AgentState, new_state
from agentlink_runtime.interactions import log_interaction

Pipeline = Callable[..., AgentState]


def _with_sender(task: TaskResult, aic: str) -> TaskResult:
    task.senderId = aic
    task.senderRole = "partner"
    return task


def build_partner_app(
    *,
    title: str,
    agent_id: str,
    tenant_id: str,
    aic_env: str,
    default_aic: str,
    pipeline: Pipeline,
    policy: dict[str, Any],
    product_name: str = "quote",
    rpc_path: str = "/rpc",
) -> FastAPI:
    aic = os.getenv(aic_env, default_aic)

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            from commerce.amp_log import start_heartbeat, stop_heartbeat

            start_heartbeat(aic=aic, agent_id=agent_id)
        except Exception:  # noqa: BLE001
            pass
        yield
        try:
            from commerce.amp_log import stop_heartbeat

            stop_heartbeat(aic=aic)
        except Exception:  # noqa: BLE001
            pass

    app = FastAPI(title=title, version="0.2.0", lifespan=_lifespan)
    if os.getenv("AIP_IDENTITY_BINDING", "0") == "1":
        app.add_middleware(AipPeerCertificateMiddleware)

    def business_id_from(command: TaskCommand, envelope: dict[str, Any] | None) -> str:
        if envelope and envelope.get("business_id"):
            return str(envelope["business_id"])
        return command.sessionId or command.taskId or f"biz-{uuid4().hex[:8]}"

    async def on_start(command: TaskCommand, task: TaskResult | None) -> TaskResult:
        if task:
            return _with_sender(task, aic)

        envelope = extract_structured(command.dataItems)
        if envelope is None:
            tr = TaskManager.create_task(
                command,
                initial_state=TaskState.AwaitingInput,
                data_items=[TextDataItem(text="请提供 StructuredDataItem 业务信封")],
            )
            return _with_sender(tr, aic)

        business_id = business_id_from(command, envelope)
        state = new_state(
            agent_id=agent_id,
            aic=aic,
            tenant_id=tenant_id,
            business_id=business_id,
            aip_task_id=command.taskId,
            session_id=command.sessionId or "",
            authz_level="negotiate",
        )
        maybe_state = pipeline(state=state, envelope=envelope, policy=policy)
        if inspect.isawaitable(maybe_state):
            state = await maybe_state  # type: ignore[assignment]
        else:
            state = maybe_state  # type: ignore[assignment]
        outcome = state.get("outcome") or {}
        aip_state = outcome.get("aip_state")

        def _inbound(res_env: dict[str, Any] | None, state_name: str, message: str | None = None) -> None:
            log_interaction(
                {
                    "direction": "inbound",
                    "local_agent_id": agent_id,
                    "from_aic": command.senderId,
                    "to_aic": aic,
                    "session_id": command.sessionId,
                    "task_id": command.taskId,
                    "state": state_name,
                    "business_id": business_id,
                    "req_schema": envelope.get("schema_type"),
                    "res_schema": (res_env or {}).get("schema_type") if res_env else None,
                    "request": envelope,
                    "response": res_env,
                    "message": message,
                }
            )
            try:
                from commerce.amp_log import record_access

                record_access(
                    task_id=command.taskId or "",
                    local_aic=aic,
                    peer_aic=str(command.senderId or ""),
                    direction="receive",
                    endpoint=os.getenv("AIP_PUBLIC_RPC_URL") or os.getenv("ACPS_PUBLIC_ENDPOINT"),
                    status=state_name,
                    extra={"schema": envelope.get("schema_type"), "business_id": business_id},
                )
            except Exception:  # noqa: BLE001
                pass

        if aip_state == "awaiting-input":
            msg = str(outcome.get("clarify", "need more info"))
            _inbound(None, "awaiting-input", msg)
            tr = TaskManager.create_task(
                command,
                initial_state=TaskState.AwaitingInput,
                data_items=[TextDataItem(text=msg)],
            )
            return _with_sender(tr, aic)

        if aip_state in ("rejected", "failed"):
            msg = str(outcome.get("reason", aip_state))
            _inbound(None, aip_state, msg)
            tr = TaskManager.create_task(
                command,
                initial_state=TaskState.Rejected if aip_state == "rejected" else TaskState.Failed,
                data_items=[TextDataItem(text=msg)],
            )
            return _with_sender(tr, aic)

        env = outcome["envelope"]
        pname = outcome.get("product_name") or product_name
        _inbound(env, "awaiting-completion")
        tr = TaskManager.create_task(command, initial_state=TaskState.AwaitingCompletion)
        TaskManager.set_products(
            tr.taskId,
            [
                Product(
                    id=f"product-{tr.taskId}",
                    name=pname,
                    description=f"{agent_id} structured product",
                    dataItems=[as_structured_item(env)],
                )
            ],
        )
        return _with_sender(TaskManager.get_task(tr.taskId) or tr, aic)

    async def on_continue(command: TaskCommand, task: TaskResult) -> TaskResult:
        TaskManager.add_command_to_history(task.taskId, command)
        return await on_start(command, None)

    handlers = CommandHandlers(
        on_start=on_start,
        on_get=DefaultHandlers.get,
        on_cancel=DefaultHandlers.cancel,
        on_complete=DefaultHandlers.complete,
        on_continue=on_continue,
    )
    add_aip_rpc_router(
        app,
        rpc_path,
        handlers,
        local_aic=aic,
        identity_binding_enabled=os.getenv("AIP_IDENTITY_BINDING", "0") == "1",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "aic": aic, "agent_id": agent_id}

    @app.post("/group/join")
    async def group_join(body: dict[str, Any]) -> dict[str, Any]:
        """ACPs Group 入组邀请（Leader 直 POST RabbitMQRequest，非 AIP TaskCommand）。"""
        from commerce.group_mq import partner_handle_join_request

        return await partner_handle_join_request(
            agent_id=agent_id, aic=aic, body=body, policy=policy
        )

    return app
