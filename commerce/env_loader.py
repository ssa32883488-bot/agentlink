"""从项目根 .env 加载配置（不依赖额外包）。"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_LOADED = False


def load_dotenv(path: Path | None = None) -> None:
    global _LOADED
    if _LOADED:
        return
    env_path = path or (_ROOT / ".env")
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)
    _LOADED = True


def llm_enabled() -> bool:
    load_dotenv()
    # 采购/供应共用同一套 LLM 开关；供应可单独用 SUPPLIER_CHAT_ENGINE 覆盖
    engine = (
        os.getenv("SUPPLIER_CHAT_ENGINE")
        or os.getenv("BUYER_CHAT_ENGINE")
        or "wit"
    ).strip().lower()
    if engine in {"rules", "rule", "off", "0", "false", "faq"}:
        return False
    return bool(os.getenv("LLM_API_KEY"))


def llm_settings() -> dict[str, str]:
    load_dotenv()
    return {
        "api_key": os.getenv("LLM_API_KEY", ""),
        "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        "model": os.getenv("LLM_MODEL", "deepseek-chat"),
        "provider": os.getenv("LLM_PROVIDER", "deepseek"),
    }


def acps_platform_configured() -> bool:
    load_dotenv()
    return bool(os.getenv("ACPS_REGISTRY_URL") and os.getenv("ACPS_CA_URL") and os.getenv("ACPS_DISCOVERY_URL"))
