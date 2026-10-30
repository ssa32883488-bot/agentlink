# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from commerce_v2.models import empty_case

_LOCK = threading.RLock()
_ROOT = Path(__file__).resolve().parents[1] / "data" / "v2_cases"
_ROOT.mkdir(parents=True, exist_ok=True)


def _path(agent_id: str) -> Path:
    return _ROOT / f"{agent_id}.json"


def _load_all(agent_id: str) -> dict[str, Any]:
    p = _path(agent_id)
    if not p.is_file():
        return {"active": None, "cases": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"active": None, "cases": {}}


def _save_all(agent_id: str, data: dict[str, Any]) -> None:
    p = _path(agent_id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def create_case(agent_id: str, *, path: str = "normal") -> dict[str, Any]:
    with _LOCK:
        data = _load_all(agent_id)
        cid = f"case-{uuid.uuid4().hex[:8]}"
        case = empty_case(agent_id, path=path)
        case["case_id"] = cid
        data["cases"][cid] = case
        data["active"] = cid
        _save_all(agent_id, data)
        return json.loads(json.dumps(case))


def get_case(agent_id: str, case_id: str | None = None) -> dict[str, Any] | None:
    with _LOCK:
        data = _load_all(agent_id)
        cid = case_id or data.get("active")
        if not cid:
            return None
        c = data["cases"].get(cid)
        return json.loads(json.dumps(c)) if c else None


def list_cases(agent_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        data = _load_all(agent_id)
        return [json.loads(json.dumps(v)) for v in data.get("cases", {}).values()]


def save_case(case: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        agent_id = case["agent_id"]
        data = _load_all(agent_id)
        data["cases"][case["case_id"]] = case
        data["active"] = case["case_id"]
        _save_all(agent_id, data)
        return json.loads(json.dumps(case))


def set_active(agent_id: str, case_id: str) -> None:
    with _LOCK:
        data = _load_all(agent_id)
        if case_id in data["cases"]:
            data["active"] = case_id
            _save_all(agent_id, data)


def append_history(case: dict[str, Any], role: str, text: str, *, meta: dict[str, Any] | None = None) -> None:
    row: dict[str, Any] = {"role": role, "text": text[:2000], "content": text[:2000]}
    if meta:
        row["meta"] = meta
    case.setdefault("history", []).append(row)


def attach_think_to_last_assistant(case: dict[str, Any], think_steps: list[dict[str, Any]]) -> None:
    """把本轮 SSE 动作轨迹挂到最近一条助手消息，供刷新后仍可展开。"""
    if not think_steps:
        return
    for h in reversed(case.get("history") or []):
        if (h.get("role") or "") in ("assistant", "ai", "system"):
            meta = dict(h.get("meta") or {})
            meta["think_steps"] = list(think_steps)
            h["meta"] = meta
            return
