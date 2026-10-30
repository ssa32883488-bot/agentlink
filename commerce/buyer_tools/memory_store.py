"""案件级工作记忆 / 关键事件；打 shared/关键 标签的条目写入跨对话共享库。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_ROOT = Path(__file__).resolve().parents[2]
_DIR = _ROOT / "data" / "agent_memory"

_SHARED_TAGS = {"shared", "关键", "key", "key_fact", "constraint", "约束"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, base: Path | None = None, *, agent_id: str | None = None) -> None:
        self.base = base or _DIR
        self.base.mkdir(parents=True, exist_ok=True)
        self.agent_id = (agent_id or os.getenv("BUYER_AGENT_ID") or "buyer-a").strip()

    def _path(self, case_id: str) -> Path:
        safe = "".join(c for c in case_id if c.isalnum() or c in "-_") or "unknown"
        return self.base / f"{self.agent_id}_{safe}.json"

    def _load(self, case_id: str) -> dict[str, Any]:
        p = self._path(case_id)
        if not p.is_file():
            return {"case_id": case_id, "entries": {}, "records": [], "updated_at": None}
        return json.loads(p.read_text(encoding="utf-8"))

    def _save(self, case_id: str, data: dict[str, Any]) -> None:
        data["case_id"] = case_id
        data["updated_at"] = _now()
        self._path(case_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def inject(self, case_id: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        from commerce import chat_sessions as cs

        data = self._load(case_id)
        bucket: dict[str, Any] = data.setdefault("entries", {})
        n = 0
        shared_n = 0
        for e in entries:
            key = str(e.get("key") or "").strip()
            if not key:
                continue
            tags = list(e.get("tags") or [])
            bucket[key] = {
                "value": e.get("value"),
                "tags": tags,
                "at": _now(),
            }
            n += 1
            tagset = {str(t).lower() for t in tags} | set(tags)
            if tagset.intersection(_SHARED_TAGS) or e.get("shared"):
                cs.upsert_shared_fact(
                    self.agent_id,
                    key,
                    e.get("value"),
                    tags=tags,
                    source_thread_id=cs.active_thread_id(self.agent_id),
                )
                shared_n += 1
        self._save(case_id, data)
        return {"ok": True, "written": n, "shared": shared_n, "case_id": case_id}

    def extract(
        self,
        case_id: str,
        *,
        keys: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        from commerce import chat_sessions as cs

        data = self._load(case_id)
        bucket: dict[str, Any] = data.get("entries") or {}
        keys = keys or []
        tags = tags or []
        out: dict[str, Any] = {}
        for k, v in bucket.items():
            if keys and k not in keys:
                continue
            if tags:
                vt = set(v.get("tags") or [])
                if not vt.intersection(tags):
                    continue
            out[k] = v.get("value")
        # 始终合入跨对话共享关键信息（窗口记忆不共享，关键事实共享）
        shared = cs.list_shared_facts(self.agent_id)
        if keys:
            shared = {k: v for k, v in shared.items() if k in keys}
        for k, v in shared.items():
            out.setdefault(k, v)
        return {"ok": True, "case_id": case_id, "entries": out, "shared_keys": list(shared.keys())}

    def record(
        self,
        case_id: str,
        *,
        event: str,
        payload: dict[str, Any] | None = None,
        ref_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        data = self._load(case_id)
        rid = f"mem-{uuid4().hex[:10]}"
        data.setdefault("records", []).append(
            {
                "record_id": rid,
                "event": event,
                "payload": payload or {},
                "ref_ids": ref_ids or [],
                "at": _now(),
            }
        )
        data["records"] = data["records"][-200:]
        self._save(case_id, data)
        return {"ok": True, "record_id": rid, "case_id": case_id}
