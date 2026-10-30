# -*- coding: utf-8 -*-
"""上传平台 mTLS 证书、切 systemd 到 run_agent_https，并开启 AIP_IDENTITY_BINDING。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko
import yaml
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
AIC_YAML = ROOT / "config" / "platform_aics.yaml"
CERTS = ROOT / "certs" / "platform"
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

BUYER = {"host": "81.70.46.119", "auth": "key", "role": "buyer"}
SUPPLIER = {
    "host": "39.105.20.113",
    "auth": "password",
    "password": os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"),
    "role": "supplier",
}

UNITS = {
    "buyer": [
        ("buyer-a", "agents.buyer_a.main:app", 8010),
        ("buyer-b", "agents.buyer_b.main:app", 8012),
        ("logistics", "agents.logistics.main:app", 8015),
    ],
    "supplier": [
        ("supplier-a", "agents.supplier_a.main:app", 8011),
        ("supplier-b", "agents.supplier_b.main:app", 8013),
        ("supplier-c", "agents.supplier_c.main:app", 8014),
    ],
}

MERGE_PY = r'''
from pathlib import Path
env = Path("/opt/agentlink/.env")
snip = Path("/tmp/platform_mtls.env").read_text(encoding="utf-8")
lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
kv, order = {}, []
for line in lines:
    if not line.strip() or line.strip().startswith("#") or "=" not in line:
        order.append(("raw", line))
        continue
    k, v = line.split("=", 1)
    kv[k] = v
    order.append(("kv", k))
for line in snip.splitlines():
    if not line.strip() or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    kv[k] = v
    if not any(t == "kv" and x == k for t, x in order):
        order.append(("kv", k))
out, seen = [], set()
for t, x in order:
    if t == "raw":
        out.append(x)
    elif x not in seen:
        out.append(f"{x}={kv[x]}")
        seen.add(x)
for k, v in kv.items():
    if k not in seen:
        out.append(f"{k}={v}")
env.write_text("\n".join(out) + "\n", encoding="utf-8")
print("merged mtls keys", sorted(k for k in kv if k.startswith("AIP_") or k.endswith("_RPC_URL")))
'''

UNIT_TMPL = """[Unit]
Description=AgentLink {name} (platform mTLS)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
Environment=HOST=0.0.0.0
Environment=PORT={port}
Environment=AGENTLINK_APP={module}
EnvironmentFile=-/opt/agentlink/.env
ExecStart=/opt/agentlink/.venv/bin/python /opt/agentlink/scripts/run_agent_https.py
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/{name}.log
StandardError=append:/var/log/agentlink/{name}.log

[Install]
WantedBy=multi-user.target
"""


def connect(spec: dict) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if spec["auth"] == "key":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(spec["host"], username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            spec["host"],
            username="root",
            password=spec["password"],
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> str:
    print(f"$ {cmd[:200]}")
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    print((out + err)[-3000:])
    if code != 0:
        raise SystemExit(f"remote exit {code}")
    return out


def upload_agent_certs(c: paramiko.SSHClient, agent_keys: list[str]) -> None:
    trust = CERTS / "trust-bundle.pem"
    if not trust.is_file():
        raise SystemExit(f"missing {trust}")
    run(c, "mkdir -p /opt/agentlink/certs/platform /var/log/agentlink")
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(trust), "/opt/agentlink/certs/platform/trust-bundle.pem")
        for key in agent_keys:
            local = CERTS / key
            for name in ("agent-cert.pem", "agent-key.pem", "server-cert.pem", "server-key.pem"):
                f = local / name
                if not f.is_file():
                    raise SystemExit(f"missing {f}")
            remote_dir = f"/opt/agentlink/certs/platform/{key}"
            run(c, f"mkdir -p {remote_dir}")
            for name in ("agent-cert.pem", "agent-key.pem", "server-cert.pem", "server-key.pem"):
                scp.put(str(local / name), f"{remote_dir}/{name}")
        # runtime files
        scp.put(str(ROOT / "agentlink_runtime" / "mtls.py"), "/opt/agentlink/agentlink_runtime/mtls.py")
        scp.put(str(ROOT / "agentlink_runtime" / "aip_client_util.py"), "/opt/agentlink/agentlink_runtime/aip_client_util.py")
        scp.put(str(ROOT / "agentlink_runtime" / "partner_app.py"), "/opt/agentlink/agentlink_runtime/partner_app.py")
        scp.put(str(ROOT / "scripts" / "run_agent_https.py"), "/opt/agentlink/scripts/run_agent_https.py")
    run(c, "chmod 600 /opt/agentlink/certs/platform/*/agent-key.pem /opt/agentlink/certs/platform/*/server-key.pem")


def write_units(c: paramiko.SSHClient, role: str) -> None:
    for name, module, port in UNITS[role]:
        body = UNIT_TMPL.format(name=name, module=module, port=port)
        remote = f"/etc/systemd/system/agentlink-{name}.service"
        local = ROOT / "dist" / f"_unit_{name}.service"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(body, encoding="utf-8")
        with SCPClient(c.get_transport()) as scp:
            scp.put(str(local), remote)


def env_pairs_for(role: str, agents: dict) -> dict[str, str]:
    pairs: dict[str, str] = {
        "AIP_IDENTITY_BINDING": "1",
        "AIP_SSL_INSECURE": "0",
        "AIP_SSL_CERT_REQS": "optional",
        "AIP_SSL_CHECK_HOSTNAME": "0",
        "AIP_TRUST_BUNDLE": "/opt/agentlink/certs/platform/trust-bundle.pem",
    }
    # per-process certs are selected via drop-in; shared defaults unused
    # Fix cross-host RPC URLs to IP/domain matching ACS
    if role == "buyer":
        pairs["SUPPLIER_A_RPC_URL"] = "https://39.105.20.113:8011/rpc"
        pairs["SUPPLIER_B_RPC_URL"] = "https://39.105.20.113:8013/rpc"
        pairs["SUPPLIER_C_RPC_URL"] = "https://39.105.20.113:8014/rpc"
        pairs["LOGISTICS_RPC_URL"] = "https://127.0.0.1:8015/rpc"
    return pairs


PER_AGENT_ENV = """# generated — do not edit by hand for cert paths
"""


def write_per_agent_env_snippets(c: paramiko.SSHClient, role: str) -> None:
    """每个 unit 通过 EnvironmentFile 叠加本 Agent 证书路径。"""
    for name, _module, _port in UNITS[role]:
        snippet = "\n".join(
            [
                f"AIP_CLIENT_CERT=/opt/agentlink/certs/platform/{name}/agent-cert.pem",
                f"AIP_CLIENT_KEY=/opt/agentlink/certs/platform/{name}/agent-key.pem",
                f"AIP_SERVER_CERT=/opt/agentlink/certs/platform/{name}/server-cert.pem",
                f"AIP_SERVER_KEY=/opt/agentlink/certs/platform/{name}/server-key.pem",
                "AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle.pem",
                "AIP_IDENTITY_BINDING=1",
                "AIP_SSL_INSECURE=0",
                "AIP_SSL_CERT_REQS=optional",
                "AIP_SSL_CHECK_HOSTNAME=0",
                "",
            ]
        )
        local = ROOT / "dist" / f"_env_{name}.env"
        local.write_text(snippet, encoding="utf-8")
        remote_env = f"/etc/agentlink/{name}.env"
        run(c, "mkdir -p /etc/agentlink")
        with SCPClient(c.get_transport()) as scp:
            scp.put(str(local), remote_env)
        # patch unit to include second EnvironmentFile
        run(
            c,
            f"grep -q '{remote_env}' /etc/systemd/system/agentlink-{name}.service || "
            f"sed -i 's|EnvironmentFile=-/opt/agentlink/.env|"
            f"EnvironmentFile=-/opt/agentlink/.env\\nEnvironmentFile=-{remote_env}|' "
            f"/etc/systemd/system/agentlink-{name}.service",
        )


def push_shared_env(c: paramiko.SSHClient, pairs: dict[str, str]) -> None:
    local = ROOT / "dist" / "_platform_mtls_push.env"
    local.write_text("\n".join(f"{k}={v}" for k, v in pairs.items()) + "\n", encoding="utf-8")
    merge_local = ROOT / "dist" / "_merge_mtls.py"
    merge_local.write_text(MERGE_PY, encoding="utf-8")
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(local), "/tmp/platform_mtls.env")
        scp.put(str(merge_local), "/tmp/merge_mtls.py")
    run(c, "python3 /tmp/merge_mtls.py")


def deploy_role(role: str, agents: dict) -> None:
    spec = BUYER if role == "buyer" else SUPPLIER
    keys = [k for k, m in agents.items() if m["host"] == role]
    print(f"==== {role} hosts={spec['host']} agents={keys} ====")
    c = connect(spec)
    upload_agent_certs(c, keys)
    push_shared_env(c, env_pairs_for(role, agents))
    write_units(c, role)
    write_per_agent_env_snippets(c, role)
    services = " ".join(f"agentlink-{n}" for n, _, _ in UNITS[role])
    health_cmds = " ".join(
        f"curl -sk https://127.0.0.1:{p}/health; echo;" for _, _, p in UNITS[role]
    )
    run(
        c,
        f"systemctl daemon-reload; systemctl restart {services}; sleep 4; "
        f"systemctl is-active {services}; {health_cmds}",
    )
    c.close()


def main() -> None:
    for key in ("buyer-a", "buyer-b", "logistics", "supplier-a", "supplier-b", "supplier-c"):
        for name in ("agent-cert.pem", "agent-key.pem", "server-cert.pem", "server-key.pem"):
            if not (CERTS / key / name).is_file():
                raise SystemExit(f"missing cert {CERTS / key / name}")
    agents = yaml.safe_load(AIC_YAML.read_text(encoding="utf-8"))["agents"]
    targets = sys.argv[1:] or ["buyer", "supplier"]
    for role in targets:
        deploy_role(role, agents)
    print("platform mTLS deploy done")


if __name__ == "__main__":
    main()
