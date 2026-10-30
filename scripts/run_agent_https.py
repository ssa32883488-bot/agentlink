# -*- coding: utf-8 -*-
"""带平台 mTLS 的 uvicorn 启动器（支持 peer 证书提取协议）。

用法（systemd）：
  EnvironmentFile=/opt/agentlink/.env
  Environment=AGENTLINK_APP=agents.supplier_a.main:app
  Environment=PORT=8011
  ExecStart=/opt/agentlink/.venv/bin/python scripts/run_agent_https.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlink_runtime.mtls import build_server_ssl_context  # noqa: E402


def main() -> None:
    app = os.environ.get("AGENTLINK_APP", "").strip()
    if not app:
        raise SystemExit("AGENTLINK_APP 未设置，例如 agents.supplier_a.main:app")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    ssl_ctx = build_server_ssl_context()

    http_proto: str | type = "h11"
    if ssl_ctx is not None and os.getenv("AIP_IDENTITY_BINDING", "0") == "1":
        from acps_sdk.aip.aip_peer_cert import AipPeerCertH11Protocol

        http_proto = AipPeerCertH11Protocol

    config_kwargs: dict = {
        "app": app,
        "host": host,
        "port": port,
        "proxy_headers": True,
        "log_level": os.environ.get("UVICORN_LOG_LEVEL", "info"),
        "http": http_proto,
        "ws": "none",
    }

    if ssl_ctx is None:
        crt = os.getenv("TLS_CRT", "/etc/agentlink/tls/server.crt")
        key = os.getenv("TLS_KEY", "/etc/agentlink/tls/server.key")
        if Path(crt).is_file() and Path(key).is_file():
            config_kwargs["ssl_certfile"] = crt
            config_kwargs["ssl_keyfile"] = key

    config = uvicorn.Config(**config_kwargs)
    config.load()
    if ssl_ctx is not None:
        config.ssl = ssl_ctx
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
