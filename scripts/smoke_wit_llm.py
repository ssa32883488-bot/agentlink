"""冒烟：Wit + DeepSeek 查库存。需 buyer-a 已启动时可改走 HTTP。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commerce.chat_buyer_wit import handle_buyer_chat_wit  # noqa: E402
from commerce.env_loader import llm_enabled, llm_settings  # noqa: E402


async def main() -> None:
    print("llm_enabled", llm_enabled())
    print("settings", {**llm_settings(), "api_key": "***"})
    res = await handle_buyer_chat_wit("查一下现在原料库存情况", run_rfq=None)
    print("intent", res.get("intent"))
    print("engine", res.get("engine"))
    print((res.get("reply") or "")[:800])


if __name__ == "__main__":
    asyncio.run(main())
