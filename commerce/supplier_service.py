from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from commerce.db import connect, dumps, init_supplier_schema, lock_for, row_to_dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure(agent_id: str) -> None:
    with lock_for(agent_id):
        conn = connect(agent_id)
        init_supplier_schema(conn)
        conn.close()


def list_catalog(agent_id: str) -> list[dict[str, Any]]:
    ensure(agent_id)
    conn = connect(agent_id)
    rows = conn.execute("SELECT * FROM catalog ORDER BY code").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def get_item(agent_id: str, code: str) -> dict[str, Any] | None:
    ensure(agent_id)
    conn = connect(agent_id)
    row = conn.execute("SELECT * FROM catalog WHERE code=?", (code,)).fetchone()
    conn.close()
    return row_to_dict(row)


def record_rfq(
    agent_id: str,
    *,
    business_id: str,
    buyer_ref: str,
    material_code: str,
    qty: float,
    request: dict[str, Any],
    response: dict[str, Any] | None,
    status: str,
) -> str:
    ensure(agent_id)
    rid = f"RFQ-{uuid4().hex[:10]}"
    conn = connect(agent_id)
    conn.execute(
        """INSERT INTO rfq_inbox(id,created_at,business_id,buyer_ref,material_code,qty,status,request_json,response_json)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            rid,
            _now(),
            business_id,
            buyer_ref,
            material_code,
            qty,
            status,
            dumps(request),
            dumps(response) if response else None,
        ),
    )
    conn.commit()
    conn.close()
    return rid


def list_rfq_inbox(agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure(agent_id)
    conn = connect(agent_id)
    rows = conn.execute(
        "SELECT * FROM rfq_inbox ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]
