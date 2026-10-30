# -*- coding: utf-8 -*-
"""为六个正式 AIC 批量申请 EAB + 客户端证书（需已 acps-cli auth login）。

用法：
  1) 安装：在 ACPs-community/acps-cli 下 uv sync
  2) 登录：uv run acps-cli --config ../../项目开发/agentlink/config/acps-cli.toml auth login
  3) 本脚本：python scripts/issue_platform_certs.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
CLI_DIR = REPO / "ACPs-community" / "acps-cli"
CFG = ROOT / "config" / "acps-cli.toml"
AIC_YAML = ROOT / "config" / "platform_aics.yaml"
OUT = ROOT / "certs" / "platform"
OUT.mkdir(parents=True, exist_ok=True)


def cli_base() -> list[str]:
    uv = shutil.which("uv")
    if uv and CLI_DIR.is_dir():
        return [uv, "run", "--directory", str(CLI_DIR), "acps-cli", "--config", str(CFG)]
    exe = shutil.which("acps-cli")
    if exe:
        return [exe, "--config", str(CFG)]
    raise SystemExit("找不到 acps-cli。请先在 ACPs-community/acps-cli 执行 uv sync")


def run(args: list[str]) -> None:
    print("+", " ".join(args))
    subprocess.check_call(args)


def main() -> None:
    agents = yaml.safe_load(AIC_YAML.read_text(encoding="utf-8"))["agents"]
    base = cli_base()
    # probe login
    try:
        subprocess.check_call(base + ["auth", "whoami"], cwd=str(CLI_DIR))
    except Exception:
        print("未登录。请先执行：")
        print(" ", " ".join(base + ["auth", "login"]))
        raise SystemExit(2)

    summary = {}
    for key, meta in agents.items():
        aic = meta["aic"]
        agent_dir = OUT / key
        agent_dir.mkdir(parents=True, exist_ok=True)
        eab = agent_dir / "eab.json"
        key_path = agent_dir / "agent-key.pem"
        cert_path = agent_dir / "agent-cert.pem"
        trust = OUT / "trust-bundle.pem"
        run(base + ["cert", "eab", "fetch", "--aic", aic, "--output", str(eab), "--json"])
        run(
            base
            + [
                "cert",
                "issue",
                "-a",
                aic,
                "--eab-file",
                str(eab),
                "-u",
                "clientAuth",
                "--key-path",
                str(key_path),
                "--cert-path",
                str(cert_path),
                "--trust-bundle-path",
                str(trust),
            ]
        )
        summary[key] = {"aic": aic, "cert": str(cert_path), "key": str(key_path)}
        print("OK", key)

    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "summary.json")
    print("下一步：把 certs/platform/<agent>/ 拷到对应云主机，配置 mTLS，再开 AIP_IDENTITY_BINDING=1")


if __name__ == "__main__":
    main()
