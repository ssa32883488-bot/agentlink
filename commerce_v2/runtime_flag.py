# -*- coding: utf-8 -*-
"""轻量运行时开关：供应/物流入口可安全 import，不拖入采购 LLM 依赖链。"""
from __future__ import annotations

import os


def use_v2() -> bool:
    return (os.getenv("AGENTLINK_RUNTIME") or "v2").lower() == "v2"
