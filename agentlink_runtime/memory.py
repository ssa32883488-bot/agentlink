from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryStore:
    """进程内四类记忆骨架；生产替换为 PostgreSQL 分区表。"""

    agent_id: str
    tenant_id: str
    working: dict[str, Any] = field(default_factory=dict)
    episodic: list[dict[str, Any]] = field(default_factory=list)
    semantic: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)

    def assert_owner(self, agent_id: str, tenant_id: str) -> None:
        if agent_id != self.agent_id or tenant_id != self.tenant_id:
            raise PermissionError("CROSS_TENANT_MEMORY_DENIED")

    def append_event(self, event: dict[str, Any]) -> None:
        self.episodic.append(event)

    def get_working(self, key: str, default: Any = None) -> Any:
        return self.working.get(key, default)

    def set_working(self, key: str, value: Any) -> None:
        self.working[key] = value
