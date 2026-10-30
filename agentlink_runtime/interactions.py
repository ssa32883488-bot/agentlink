"""本机 AIP 交互总线：供同机 UI 观测（按 agent_id 隔离过滤）。"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_DEFAULT = Path(os.getenv("AGENTLINK_INTERACTIONS_LOG", "logs/interactions.jsonl"))


def _path() -> Path:
    p = Path(os.getenv("AGENTLINK_INTERACTIONS_LOG", str(_DEFAULT)))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_interaction(event: dict[str, Any]) -> None:
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    line = json.dumps(row, ensure_ascii=False)
    with _LOCK:
        with _path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_interactions(
    *,
    agent_id: str | None = None,
    business_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with _LOCK:
        lines = path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if agent_id and row.get("local_agent_id") != agent_id:
            continue
        if business_id and row.get("business_id") != business_id:
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows
