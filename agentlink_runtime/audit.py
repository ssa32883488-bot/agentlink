from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AuditEvent:
    ts: str
    agent_id: str
    tenant_id: str
    business_id: str | None
    tool: str
    idempotency_key: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("logs") / "audit.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._mem: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        with self._lock:
            self._mem.append(event)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def by_business(self, business_id: str) -> list[AuditEvent]:
        return [e for e in self._mem if e.business_id == business_id]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
