"""平台 mTLS：从环境变量构建客户端/服务端 SSL 上下文。"""
from __future__ import annotations

import os
import ssl
from pathlib import Path


def _path(env: str) -> Path | None:
    raw = (os.getenv(env) or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_file() else None


def build_client_ssl_context() -> ssl.SSLContext | None:
    """出站 AIP：优先平台 clientAuth + trust-bundle；否则 AIP_SSL_INSECURE=1 时跳过校验。"""
    cert = _path("AIP_CLIENT_CERT")
    key = _path("AIP_CLIENT_KEY")
    ca = _path("AIP_TRUST_BUNDLE")
    if cert and key and ca:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
        ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        # 平台证书 SAN 含域名/IP；跨机用 IP 访问时关闭 hostname 检查仍校验证书链
        if os.getenv("AIP_SSL_CHECK_HOSTNAME", "0") != "1":
            ctx.check_hostname = False
        return ctx
    if os.getenv("AIP_SSL_INSECURE", "0") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def build_server_ssl_context() -> ssl.SSLContext | None:
    """入站 HTTPS：平台 serverAuth；可选要求客户端证书（CERT_OPTIONAL/REQUIRED）。"""
    cert = _path("AIP_SERVER_CERT")
    key = _path("AIP_SERVER_KEY")
    if not cert or not key:
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ca = _path("AIP_TRUST_BUNDLE")
    mode = (os.getenv("AIP_SSL_CERT_REQS") or "optional").strip().lower()
    if ca and mode in ("optional", "required", "1", "2"):
        ctx.load_verify_locations(cafile=str(ca))
        ctx.verify_mode = (
            ssl.CERT_REQUIRED if mode in ("required", "2") else ssl.CERT_OPTIONAL
        )
    else:
        ctx.verify_mode = ssl.CERT_NONE
    return ctx
