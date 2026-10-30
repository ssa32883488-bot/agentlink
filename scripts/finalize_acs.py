# -*- coding: utf-8 -*-
"""定稿六份 ACS：后浪队 provider + IP:port 端点。"""
from __future__ import annotations

import json
from pathlib import Path

ACS_DIR = Path(__file__).resolve().parents[1] / "acs"

PROVIDER = {
    "countryCode": "CN",
    "organization": "后浪队",
    "department": "AgentLink",
    "url": "https://ashui.online:8010",
    "license": "腾讯云端点 HTTPS+Let's Encrypt(ashui.online)；阿里云端点 HTTPS 公网IP(自签)。审核通过后换平台 CA mTLS",
    "name": "李佳铖",
    "email": "3572962849@qq.com",
    "domainRegistrations": [
        {
            "domain": "ashui.online",
            "registrationNumber": "NONE",
            "registrationType": "WHOIS",
        }
    ],
}

# 腾讯云用域名；阿里云不用域名，只用公网 IP HTTPS
ENDPOINTS = {
    "buyer-agent-a.acs.json": {
        "url": "https://ashui.online:8010/rpc",
        "ip": "81.70.46.119",
        "dns": ["ashui.online", "www.ashui.online"],
        "provider_domain": "ashui.online",
        "provider_url": "https://ashui.online:8010",
    },
    "buyer-agent-b.acs.json": {
        "url": "https://ashui.online:8012/rpc",
        "ip": "81.70.46.119",
        "dns": ["ashui.online", "www.ashui.online"],
        "provider_domain": "ashui.online",
        "provider_url": "https://ashui.online:8010",
    },
    "supplier-agent-a.acs.json": {
        "url": "https://39.105.20.113:8011/rpc",
        "ip": "39.105.20.113",
        "dns": [],
        "provider_domain": "39.105.20.113",
        "provider_url": "https://39.105.20.113:8011",
    },
    "supplier-agent-b.acs.json": {
        "url": "https://39.105.20.113:8013/rpc",
        "ip": "39.105.20.113",
        "dns": [],
        "provider_domain": "39.105.20.113",
        "provider_url": "https://39.105.20.113:8011",
    },
    "supplier-agent-c.acs.json": {
        "url": "https://39.105.20.113:8014/rpc",
        "ip": "39.105.20.113",
        "dns": [],
        "provider_domain": "39.105.20.113",
        "provider_url": "https://39.105.20.113:8011",
    },
    "logistics-agent.acs.json": {
        "url": "https://ashui.online:8015/rpc",
        "ip": "81.70.46.119",
        "dns": ["ashui.online", "www.ashui.online"],
        "provider_domain": "ashui.online",
        "provider_url": "https://ashui.online:8010",
    },
}


def main() -> None:
    from wit.acps.acs_contract import (
        REGISTRATION_CANDIDATE_LAST_MODIFIED_TIME,
        normalize_registration_candidate_acs,
        validate_registry_acs,
    )

    for name, ep in ENDPOINTS.items():
        path = ACS_DIR / name
        data = json.loads(path.read_text(encoding="utf-8"))
        provider = dict(PROVIDER)
        pdom = ep.get("provider_domain") or ep["ip"]
        provider["url"] = ep.get("provider_url") or f"https://{pdom}"
        provider["domainRegistrations"] = [
            {
                "domain": pdom,
                "registrationNumber": "NONE",
                "registrationType": "WHOIS",
            }
        ]
        data["provider"] = provider
        data["securitySchemes"] = {
            "mtls": {
                "type": "mutualTLS",
                "description": "智能体间 mTLS 双向认证",
            }
        }
        data["endPoints"] = [
            {
                "url": ep["url"],
                "transport": "JSONRPC",
                "security": [{"mtls": []}],
            }
        ]
        cert = data.get("certificate") or {}
        alt = {"ip": [ep["ip"]]}
        if ep.get("dns"):
            alt["dns"] = ep["dns"]
        cert["altNames"] = alt
        cert["requestedValidity"] = cert.get("requestedValidity") or 825
        data["certificate"] = cert
        # 平台 schema 必填：aic/active/lastModifiedTime（注册候选占位，审核后由平台覆盖）
        data["aic"] = ""
        data["active"] = False
        data["lastModifiedTime"] = REGISTRATION_CANDIDATE_LAST_MODIFIED_TIME
        data = normalize_registration_candidate_acs(data)
        for endpoint in data.get("endPoints") or []:
            endpoint["security"] = [{"mtls": []}]
        data.setdefault("securitySchemes", {})["mtls"] = {
            "type": "mutualTLS",
            "description": "智能体间 mTLS 双向认证",
        }
        validate_registry_acs(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("updated", name, "->", ep["url"])


if __name__ == "__main__":
    main()
