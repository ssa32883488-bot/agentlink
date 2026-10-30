from __future__ import annotations

from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    agent_id: str
    aic: str
    tenant_id: str
    business_id: str
    aip_task_id: str | None
    session_id: str
    authz_level: Literal["suggest", "negotiate", "commit"]
    working_facts: dict[str, Any]
    pending_tool_calls: list[dict[str, Any]]
    last_tool_results: list[dict[str, Any]]
    human_gate: dict[str, Any] | None
    outcome: dict[str, Any] | None
    error: str | None


def new_state(**kwargs: Any) -> AgentState:
    base: AgentState = {
        "agent_id": "",
        "aic": "",
        "tenant_id": "",
        "business_id": "",
        "aip_task_id": None,
        "session_id": "",
        "authz_level": "negotiate",
        "working_facts": {},
        "pending_tool_calls": [],
        "last_tool_results": [],
        "human_gate": None,
        "outcome": None,
        "error": None,
    }
    base.update(kwargs)  # type: ignore[typeddict-item]
    return base
