"""Deploy supplier passive logistics: Aliyun suppliers + Tencent logistics."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
SUPPLIER_PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce/discovery.py",
    "agents/logistics/graph.py",
    "agents/logistics/policy.yaml",
]

SUPPLIER_FILES = [
    "commerce/discovery.py",
    "commerce/progress.py",
    "agentlink_runtime/partner_app.py",
    "agents/supplier_common/__init__.py",
    "agents/supplier_common/freight.py",
    "agents/supplier_common/negotiate.py",
    "agents/supplier_a/graph.py",
    "agents/supplier_a/policy.yaml",
    "agents/supplier_a/AGENTS.md",
    "agents/supplier_b/graph.py",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_b/AGENTS.md",
    "agents/supplier_c/graph.py",
    "agents/supplier_c/policy.yaml",
    "agents/supplier_c/AGENTS.md",
]


def connect_buyer() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    return c


def connect_supplier() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        SUPPLIER,
        username="root",
        password=SUPPLIER_PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    return c


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = c.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out, flush=True)
    return out


def main() -> None:
    print("==== Tencent: logistics + discovery ====", flush=True)
    b = connect_buyer()
    put(b, BUYER_FILES)
    run(
        b,
        "systemctl restart agentlink-logistics; sleep 3; "
        "systemctl is-active agentlink-logistics; "
        "curl -sk -o /dev/null -w 'logistics=%{http_code}\\n' https://127.0.0.1:8015/health",
    )
    b.close()

    print("==== Aliyun: suppliers + freight ====", flush=True)
    s = connect_supplier()
    put(s, SUPPLIER_FILES)
    run(
        s,
        r"""
set -e
cd /opt/agentlink
mkdir -p agents/supplier_common /etc/agentlink
grep -q '^ACPS_DISCOVERY_URL=' .env || echo 'ACPS_DISCOVERY_URL=https://wt.ioa.pub/discovery' >> .env
for u in a b c; do
  f=/etc/agentlink/supplier-${u}.env
  touch "$f"
  grep -q '^LOGISTICS_RPC_URL=' "$f" && sed -i 's|^LOGISTICS_RPC_URL=.*|LOGISTICS_RPC_URL=https://81.70.46.119:8015/rpc|' "$f" || echo 'LOGISTICS_RPC_URL=https://81.70.46.119:8015/rpc' >> "$f"
  grep -q '^LOGISTICS_AIC=' "$f" || echo 'LOGISTICS_AIC=1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS' >> "$f"
done
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 5
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
curl -sk -o /dev/null -w 'a=%{http_code} ' https://127.0.0.1:8011/health
curl -sk -o /dev/null -w 'b=%{http_code} ' https://127.0.0.1:8013/health
curl -sk -o /dev/null -w 'c=%{http_code}\n' https://127.0.0.1:8014/health
""",
    )
    s.close()
    print("DEPLOY_SUPPLIER_FREIGHT_DONE", flush=True)


if __name__ == "__main__":
    main()
