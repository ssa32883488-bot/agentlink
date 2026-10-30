"""AMP 本地日志汇总（应用成效看板数据源）。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_ACCESS = _ROOT / "logs" / "amp_access.jsonl"
_MESSAGE = _ROOT / "logs" / "amp_message.jsonl"


def _read_jsonl(path: Path, limit: int = 5000) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(rows) >= limit:
                break
    return rows


def summarize_amp() -> dict[str, Any]:
    access = _read_jsonl(_ACCESS)
    messages = _read_jsonl(_MESSAGE)
    by_day: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    task_ids: set[str] = set()
    for row in access:
        ts = str(row.get("timestamp") or "")[:10]
        if ts:
            by_day[ts] += 1
        code = ((row.get("body") or {}).get("response") or {}).get("statusCode")
        if code is None:
            # 旧日志可能把 AIP taskState 写在顶层
            code = row.get("status") or ((row.get("body") or {}).get("attributes") or {}).get("taskState") or "ok"
        statuses[str(code)] += 1
        tid = row.get("correlationId") or row.get("correlation_id") or ""
        if tid:
            task_ids.add(str(tid))
    msg_ids = {
        str((m.get("body") or {}).get("messageId") or (m.get("resource") or {}).get("agentlink.messageId") or "")
        for m in messages
    }
    msg_ids.discard("")
    trend = [{"date": d, "access": by_day[d]} for d in sorted(by_day.keys())[-14:]]
    ok_keys = {
        "200",
        "ok",
        "success",
        "awaiting-completion",
        "awaiting-input",
        "completed",
        "accepted",
    }
    ok = sum(v for k, v in statuses.items() if str(k) in ok_keys or str(k).startswith("2"))
    total = sum(statuses.values()) or 1
    return {
        "access_count": len(access),
        "message_count": len(messages),
        "unique_task_ids": len(task_ids),
        "unique_message_ids": len(msg_ids),
        "success_rate": round(ok / total, 4),
        "status_breakdown": dict(statuses),
        "access_trend_14d": trend,
        "kpi": {
            "access": len(access),
            "messages": len(messages),
            "tasks": len(task_ids),
            "success_rate_pct": round(100.0 * ok / total, 1),
        },
    }
