"""座椅商城 — 独立链接（默认 :8080），只服务 C 端下单。"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
BUYER_API = os.getenv("BUYER_A_API", "https://127.0.0.1:8010")
_HTTPX_VERIFY = os.getenv("UI_HTTPX_VERIFY", "0") == "1"

app = FastAPI(title="座椅商城", version="0.4.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "mall.html")


@app.get("/api/products")
async def products() -> JSONResponse:
    async with httpx.AsyncClient(timeout=10.0, verify=_HTTPX_VERIFY) as client:
        r = await client.get(f"{BUYER_API}/api/mall/products")
    return JSONResponse(content=r.json(), status_code=r.status_code)


@app.post("/api/orders")
async def orders(request: Request) -> JSONResponse:
    body = await request.body()
    async with httpx.AsyncClient(timeout=30.0, verify=_HTTPX_VERIFY) as client:
        r = await client.post(
            f"{BUYER_API}/api/mall/orders",
            content=body,
            headers={"content-type": "application/json"},
        )
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        data = {"raw": r.text}
    return JSONResponse(content=data, status_code=r.status_code)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "seat-mall", "buyer_api": BUYER_API}


def main() -> None:
    import uvicorn

    port = int(os.getenv("MALL_PORT", "8080"))
    uvicorn.run("ui.mall_app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
