"""域控制台 UI：同机三个 Agent 顶栏切换，内容按 agent_id 隔离。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agentlink_runtime.interactions import read_interactions

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DEFAULT_CONFIG = ROOT / "config_buyer_a.yaml"


def load_config() -> dict[str, Any]:
    path = Path(os.getenv("AGENTLINK_UI_CONFIG", str(DEFAULT_CONFIG)))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["_config_path"] = str(path)
    return data


CFG = load_config()
AGENTS = {a["id"]: a for a in CFG["agents"]}
# 本机 Agent 多为 HTTPS + 自签/IP，UI 反代关闭证书校验
_HTTPX_VERIFY = os.getenv("UI_HTTPX_VERIFY", "0") == "1"

app = FastAPI(title=CFG.get("domain_title", "AgentLink UI"), version="0.3.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/domain")
async def domain() -> dict[str, Any]:
    return {
        "domain_id": CFG["domain_id"],
        "domain_title": CFG["domain_title"],
        "config_path": CFG.get("_config_path"),
        "agents": CFG["agents"],
    }


@app.get("/api/agents/{agent_id}/health")
async def agent_health(agent_id: str) -> dict[str, Any]:
    meta = AGENTS.get(agent_id)
    if not meta:
        raise HTTPException(404, "unknown agent on this domain")
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=_HTTPX_VERIFY) as client:
            r = await client.get(f"{meta['api_base']}/health")
            r.raise_for_status()
            body = r.json()
            body["_ui"] = {"title": meta["title"], "role": meta["role"], "online": True}
            return body
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "down",
            "agent_id": agent_id,
            "error": str(exc),
            "_ui": {"title": meta["title"], "role": meta["role"], "online": False},
        }


@app.get("/api/agents/{agent_id}/interactions")
async def agent_interactions(
    agent_id: str,
    business_id: str | None = None,
    limit: int = Query(80, ge=1, le=500),
) -> dict[str, Any]:
    if agent_id not in AGENTS:
        raise HTTPException(404, "unknown agent on this domain")
    rows = read_interactions(agent_id=agent_id, business_id=business_id, limit=limit)
    return {"agent_id": agent_id, "items": rows}


@app.get("/api/domain/health")
async def domain_health() -> dict[str, Any]:
    out = []
    for a in CFG["agents"]:
        h = await agent_health(a["id"])
        out.append({"id": a["id"], "title": a["title"], "health": h})
    return {"domain_id": CFG["domain_id"], "agents": out}


@app.api_route("/api/proxy/{agent_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(agent_id: str, path: str, request: Request):
    """把浏览器操作代理到本机对应 Agent，保证跨域简单且上下文隔离。"""
    meta = AGENTS.get(agent_id)
    if not meta:
        raise HTTPException(404, "unknown agent on this domain")
    # 供应/物流控制台禁止代发采购补货流；本侧 ERP（对话/工单/通知等）写操作放行
    if meta.get("role") == "partner" and request.method != "GET":
        p = path.lstrip("/")
        erp_ok = p == "api/erp" or p.startswith("api/erp/")
        if not erp_ok:
            raise HTTPException(403, "供应/物流侧控制台仅只读观测，补货请在采购商A发起")

    url = f"{meta['api_base'].rstrip('/')}/{path.lstrip('/')}"
    body = await request.body()
    headers = {"content-type": request.headers.get("content-type", "application/json")}
    wants_stream = "stream" in path.rstrip("/").split("/")[-1:] or path.rstrip("/").endswith("/stream")
    timeout = httpx.Timeout(180.0, connect=10.0) if wants_stream else httpx.Timeout(60.0)

    if wants_stream:
        client = httpx.AsyncClient(timeout=timeout, verify=_HTTPX_VERIFY)

        async def event_proxy():
            try:
                async with client.stream(request.method, url, content=body, headers=headers) as r:
                    async for chunk in r.aiter_bytes():
                        if chunk:
                            yield chunk
            finally:
                await client.aclose()

        return StreamingResponse(
            event_proxy(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async with httpx.AsyncClient(timeout=timeout, verify=_HTTPX_VERIFY) as client:
        r = await client.request(request.method, url, content=body, headers=headers)
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        data = {"raw": r.text}
    return JSONResponse(content=data, status_code=r.status_code)


def main() -> None:
    import uvicorn

    port = int(os.getenv("UI_PORT", str(CFG.get("ui_port", 8090))))
    uvicorn.run("ui.app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
