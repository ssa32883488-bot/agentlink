from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agentlink_runtime.audit import AuditEvent, AuditLog, now_iso
from agentlink_runtime.authz import AuthzLevel, allows


Handler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class ToolSpec:
    name: str
    authz_min: AuthzLevel
    handler: Handler
    human_confirm: bool = False
    side_effects: str = "none"
    description: str = ""


@dataclass
class AgentContext:
    agent_id: str
    aic: str
    tenant_id: str
    authz_level: AuthzLevel
    business_id: str | None = None
    human_approvals: set[str] = field(default_factory=set)


@dataclass
class ToolResult:
    ok: bool
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ToolGateway:
    def __init__(self, audit: AuditLog | None = None) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._cache: dict[str, ToolResult] = {}
        self.audit = audit or AuditLog()

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def list_catalog(self) -> list[str]:
        return sorted(self._tools.keys())

    async def execute(
        self,
        ctx: AgentContext,
        name: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(False, "UNKNOWN_TOOL", error=f"unknown tool: {name}")

        if not allows(ctx.authz_level, spec.authz_min):
            result = ToolResult(False, "AUTHZ_INSUFFICIENT", error=f"need {spec.authz_min}")
            self._audit(ctx, name, idempotency_key or "-", result)
            return result

        if spec.human_confirm and name not in ctx.human_approvals:
            result = ToolResult(False, "NEED_HUMAN", error="human confirmation required")
            self._audit(ctx, name, idempotency_key or "-", result)
            return result

        key = idempotency_key or self._default_key(ctx, name, arguments)
        if key in self._cache:
            return self._cache[key]

        try:
            data = await spec.handler(arguments, {
                "agent_id": ctx.agent_id,
                "aic": ctx.aic,
                "tenant_id": ctx.tenant_id,
                "business_id": ctx.business_id,
            })
            result = ToolResult(True, "OK", data=data)
        except Exception as exc:  # noqa: BLE001 — smoke gateway surfaces errors
            result = ToolResult(False, "HANDLER_ERROR", error=str(exc))

        self._cache[key] = result
        self._audit(ctx, name, key, result)
        return result

    def _audit(self, ctx: AgentContext, name: str, key: str, result: ToolResult) -> None:
        self.audit.record(
            AuditEvent(
                ts=now_iso(),
                agent_id=ctx.agent_id,
                tenant_id=ctx.tenant_id,
                business_id=ctx.business_id,
                tool=name,
                idempotency_key=key,
                status=result.status,
                detail={"ok": result.ok, "error": result.error, "data_keys": list(result.data.keys())},
            )
        )

    @staticmethod
    def _default_key(ctx: AgentContext, name: str, arguments: dict[str, Any]) -> str:
        raw = json.dumps({"a": ctx.agent_id, "b": ctx.business_id, "t": name, "p": arguments}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:24]
