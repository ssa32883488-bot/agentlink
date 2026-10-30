"""ACPs 平台入驻脚手架（Wit AcpsConfig / Provisioner）。

正式上平台前请填写 .env 中 ACPS_* 或 config/acps_platform.yaml。
本脚本不代替人工审核；只组装注册候选并尝试调用 Wit 入驻 API。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commerce.env_loader import acps_platform_configured, load_dotenv  # noqa: E402


def _load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_acps_config():
    from wit import (
        AcpsConfig,
        AgentCertificateRequest,
        AgentDomainRegistration,
        AgentProviderProfile,
    )

    load_dotenv()
    yaml_path = ROOT / "config" / "acps_platform.yaml"
    cfg: dict = {}
    if yaml_path.is_file():
        cfg = _load_yaml(yaml_path)

    registry = os.getenv("ACPS_REGISTRY_URL") or cfg.get("registry_url") or ""
    ca = os.getenv("ACPS_CA_URL") or cfg.get("ca_url") or ""
    discovery = os.getenv("ACPS_DISCOVERY_URL") or cfg.get("discovery_url") or ""
    if not (registry and ca and discovery):
        raise SystemExit(
            "缺少平台地址。请配置 .env 的 ACPS_REGISTRY_URL / ACPS_CA_URL / ACPS_DISCOVERY_URL，"
            "或复制 config/acps_platform.example.yaml → config/acps_platform.yaml 后重试。"
        )

    provider_cfg = cfg.get("provider") or {}
    cert_cfg = cfg.get("certificate") or {}
    provider = AgentProviderProfile(
        organization=provider_cfg.get("organization"),
        country_code=provider_cfg.get("country_code") or "CN",
        url=provider_cfg.get("url"),
        email=provider_cfg.get("email"),
        domain_registrations=tuple(
            AgentDomainRegistration(domain=d, registration_number="PENDING", registration_type="domain")
            for d in (cert_cfg.get("dns") or [])[:1]
        )
        or (),
    )
    certificate = AgentCertificateRequest(
        dns=tuple(cert_cfg.get("dns") or ()),
        requested_validity=cert_cfg.get("requested_validity"),
    )
    return AcpsConfig(
        registry_url=registry,
        registry_mtls_url=os.getenv("ACPS_REGISTRY_MTLS_URL") or cfg.get("registry_mtls_url"),
        ca_url=ca,
        discovery_url=discovery,
        public_endpoint=os.getenv("ACPS_PUBLIC_ENDPOINT") or cfg.get("public_endpoint"),
        mq_url=os.getenv("ACPS_MQ_URL") or cfg.get("mq_url") or None,
        provider=provider,
        certificate=certificate,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="ACPs 平台入驻预检 / 组装")
    parser.add_argument("--agent", default="buyer-a")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--submit", action="store_true", help="尝试真实提交（需平台可达与账号）")
    args = parser.parse_args()

    load_dotenv()
    print(f"agent={args.agent}")
    print(f"platform_env_configured={acps_platform_configured()}")

    acps = build_acps_config()
    draft = {
        "registry_url": acps.registry_url,
        "ca_url": acps.ca_url,
        "discovery_url": acps.discovery_url,
        "public_endpoint": acps.public_endpoint,
        "provider": acps.provider.to_acs() if acps.provider else None,
        "certificate": acps.certificate.to_acs() if acps.certificate else None,
    }
    out = ROOT / "workspaces" / args.agent / "registration_candidate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")

    if not args.submit:
        print("dry-run 完成。正式提交加 --submit，并配置 Registry 账号与审核流。")
        print("证书也可按平台文档使用 acps-cli 另行申领。")
        return 0

    from wit import RegistryPasswordCredentials, WitAgent, WitRuntime

    user = os.getenv("ACPS_REGISTRY_USER")
    password = os.getenv("ACPS_REGISTRY_PASSWORD")
    if not (user and password):
        raise SystemExit("提交需要 ACPS_REGISTRY_USER / ACPS_REGISTRY_PASSWORD")

    # 最小可编译 Agent，用于触发 Wit 入驻管线
    agent = WitAgent(
        id=args.agent,
        instructions="platform enrollment scaffold",
        model=None,
    )
    runtime = WitRuntime(agent, workspace=out.parent, acps=acps)
    compiled = runtime.agent if hasattr(runtime, "agent") else agent
    print("runtime ready; attempting provisioner enroll…")
    # Wit 版本差异：优先 provisioner API
    provisioner = getattr(runtime, "_provisioner", None) or getattr(runtime, "provisioner", None)
    if provisioner is None and hasattr(runtime, "enroll"):
        result = runtime.enroll(  # type: ignore[attr-defined]
            credentials=RegistryPasswordCredentials(username=user, password=password)
        )
        print(result)
        return 0
    if provisioner is None:
        print("当前 WitRuntime 未暴露 enroll/provisioner；候选 ACS 已写出，请用平台控制台或 acps-cli 完成审核/证书。")
        print("compiled=", type(compiled))
        return 0
    creds = RegistryPasswordCredentials(username=user, password=password)
    if hasattr(provisioner, "enroll"):
        result = provisioner.enroll(credentials=creds)
    else:
        result = provisioner.run(credentials=creds)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
