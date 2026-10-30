# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import aio_pika
from acps_sdk.aip.aip_group_runtime import build_external_connection_url
from commerce.group_mq import build_agent_ssl_context


async def try_vhost(vhost: str) -> None:
    ctx = build_agent_ssl_context("buyer-a")
    url = build_external_connection_url(
        host="wt.ioa.pub",
        port=5671,
        vhost=vhost,
        connection_name="agent-1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW",
    )
    print("TRY", repr(vhost), url, flush=True)
    try:
        conn = await asyncio.wait_for(aio_pika.connect(url, ssl_context=ctx), timeout=20)
        print("OK", repr(vhost), flush=True)
        await conn.close()
    except Exception as exc:  # noqa: BLE001
        print("FAIL", repr(vhost), type(exc).__name__, repr(exc), flush=True)


async def main() -> None:
    for v in ["/", "acps", "ACPs", "wit", "default"]:
        await try_vhost(v)


if __name__ == "__main__":
    asyncio.run(main())
