"""采购侧 Group 竞价场 API（P0：建组 / ping / 解散）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from commerce import group_mq as gm

router = APIRouter(tags=["commerce-group"])


class GroupOpenIn(BaseModel):
    members: list[str] | None = Field(
        default=None,
        description="默认 supplier-a/b/c + logistics",
    )
    invite: bool = True


def mount_group_routes(app, *, aic: str, agent_id: str = "buyer-a") -> None:
    @router.post("/api/erp/group/open")
    async def group_open(body: GroupOpenIn | None = None) -> dict[str, Any]:
        body = body or GroupOpenIn()
        try:
            rec = await gm.open_group(
                leader_aic=aic,
                leader_agent_id=agent_id,
                member_agent_ids=body.members,
                invite=body.invite,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"建组失败: {exc}") from exc
        return {
            "session_id": rec.session_id,
            "group_id": rec.group_id,
            "status": rec.status,
            "members": rec.members,
            "created_at": rec.created_at,
            "results": rec.results,
        }

    @router.post("/api/erp/group/{session_id}/ping")
    async def group_ping(session_id: str) -> dict[str, Any]:
        try:
            return await gm.ping_group(session_id)
        except KeyError:
            raise HTTPException(404, "session 不存在") from None
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"ping 失败: {exc}") from exc

    @router.post("/api/erp/group/{session_id}/dissolve")
    async def group_dissolve(session_id: str) -> dict[str, Any]:
        await gm.dissolve_group(session_id)
        return {"ok": True, "session_id": session_id}

    @router.get("/api/erp/group/sessions")
    def group_sessions() -> dict[str, Any]:
        items = [
            {
                "session_id": s.session_id,
                "group_id": s.group_id,
                "status": s.status,
                "members": s.members,
                "task_id": s.task_id,
                "result_count": len(s.results),
            }
            for s in gm.list_sessions()
        ]
        return {"items": items}

    app.include_router(router)
