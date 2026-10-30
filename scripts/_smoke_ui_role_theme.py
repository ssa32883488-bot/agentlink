# -*- coding: utf-8 -*-
"""部署三端换肤静态资源并白话冒烟。"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import ssl
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "ui/static/styles.css",
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/config_buyer_a.yaml",
    "ui/config_buyer_b.yaml",
    "ui/config_supplier_a.yaml",
    "ui/config_supplier_b.yaml",
    "ui/config_supplier_c.yaml",
    "ui/config_logistics.yaml",
    "docs/design_ui_role_themes.md",
    "docs/evidence/ui_role_theme_test.md",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        local = ROOT / rel
        if not local.is_file():
            continue
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = c.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(local), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=120, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", errors="replace")


def http_json(url: str) -> dict:
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(url, context=ctx, timeout=20) as r:
        return json.loads(r.read().decode())


def http_text(url: str) -> str:
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(url, context=ctx, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def main() -> int:
    print("==== deploy tencent ====", flush=True)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(b, FILES)
    run(
        b,
        """
set -e
systemctl restart agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics
sleep 3
systemctl is-active agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics
""",
    )
    b.close()

    print("==== deploy aliyun ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(s, FILES)
    run(
        s,
        """
set -e
systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
sleep 3
systemctl is-active agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
""",
    )
    s.close()

    checks = []
    # domain titles
    for url, expect in [
        ("https://ashui.online:8090/api/domain", "采联"),
        ("https://ashui.online:8095/api/domain", "物流"),
        ("https://39.105.20.113:8091/api/domain", "供应"),
    ]:
        try:
            d = http_json(url)
            title = d.get("domain_title") or ""
            ok = expect in title
            checks.append((f"domain {url}", ok, title))
            print("DOMAIN", url, title, "OK" if ok else "FAIL", flush=True)
        except Exception as exc:  # noqa: BLE001
            checks.append((f"domain {url}", False, str(exc)))
            print("DOMAIN FAIL", url, exc, flush=True)

    # static markers
    for url, needles in [
        ("https://ashui.online:8090/", ["roleChip", "styles.css"]),
        ("https://ashui.online:8090/static/styles.css", ["role-buyer", "role-supplier", "role-logistics", "1.45rem"]),
        ("https://ashui.online:8090/static/app.js", ["applyRoleTheme", "resolveUiRole"]),
    ]:
        try:
            text = http_text(url)
            ok = all(n in text for n in needles)
            checks.append((f"static {url}", ok, ",".join(needles)))
            print("STATIC", url, "OK" if ok else "FAIL", flush=True)
        except Exception as exc:  # noqa: BLE001
            checks.append((f"static {url}", False, str(exc)))
            print("STATIC FAIL", url, exc, flush=True)

    failed = [c for c in checks if not c[1]]
    print("SUMMARY", "PASS" if not failed else "FAIL", f"{len(checks)-len(failed)}/{len(checks)}", flush=True)
    # write evidence snippet on local
    ev = ROOT / "docs" / "evidence" / "ui_role_theme_test.md"
    lines = [
        "",
        "## 自动化实测结果",
        "",
        f"- 结论：**{'PASS' if not failed else 'FAIL'}**（{len(checks)-len(failed)}/{len(checks)}）",
    ]
    for name, ok, detail in checks:
        lines.append(f"- {'✓' if ok else '✗'} {name} → `{detail}`")
    with ev.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
