# -*- coding: utf-8 -*-
"""将本地 Group/流程相关最新文件同步到腾讯+阿里云，重启并健康检查。"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce/group_mq.py",
    "commerce/group_routes.py",
    "commerce/flow_service.py",
    "commerce/buyer_routes.py",
    "agentlink_runtime/partner_app.py",
    ".env.example",
    "docs/evidence/group_p0_smoke.md",
    "docs/evidence/group_p2_tco_smoke.md",
    "docs/evidence/group_e2e_case_smoke.md",
]
SUPPLIER_FILES = [
    "commerce/group_mq.py",
    "agentlink_runtime/partner_app.py",
    ".env.example",
]

ENV_LINES = [
    "ACPS_MQ_HOST=wt.ioa.pub",
    "ACPS_MQ_PORT=5671",
    "ACPS_MQ_VHOST=acps",
    "ACPS_MQ_AUTH_URL=https://wt.ioa.pub/mq-auth",
    "ACPS_GROUP_IDENTITY_BINDING=1",
    "ACPS_GROUP_AUCTION=1",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        local = ROOT / rel
        if not local.is_file():
            print("skip missing", rel, flush=True)
            continue
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = c.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(local), remote)
        print(f"put {rel} sha={sha256(local)}", flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", errors="replace")


def ensure_env(c: paramiko.SSHClient) -> None:
    lines = "\n".join(
        f"grep -q '^{k.split('=')[0]}=' .env || echo '{k}' >> .env" for k in ENV_LINES
    )
    run(
        c,
        f"""
set -e
cd /opt/agentlink
touch .env
{lines}
sed -i 's|^ACPS_MQ_VHOST=/.*|ACPS_MQ_VHOST=acps|' .env || true
grep -E '^ACPS_MQ_|^ACPS_GROUP_' .env | sort -u
""",
    )


def verify_hashes(c: paramiko.SSHClient, files: list[str]) -> bool:
    ok = True
    for rel in files:
        local = ROOT / rel
        if not local.is_file():
            continue
        local_sha = sha256(local)
        out = run(
            c,
            f"sha256sum /opt/agentlink/{rel} 2>/dev/null | cut -c1-12 || echo MISSING",
        ).strip()
        remote_sha = (out.splitlines()[-1] if out.splitlines() else "").strip()
        match = remote_sha.startswith(local_sha)
        print(f"verify {rel}: local={local_sha} remote={remote_sha} {'OK' if match else 'DIFF'}", flush=True)
        ok = ok and match
    return ok


def main() -> int:
    print("==== Tencent buyer/logistics ====", flush=True)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(b, BUYER_FILES)
    ensure_env(b)
    run(
        b,
        """
set -e
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
sleep 4
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
curl -sk https://127.0.0.1:8010/health; echo
curl -sk https://127.0.0.1:8015/health; echo
curl -sk https://127.0.0.1:8090/ | head -c 80; echo
""",
    )
    ok_b = verify_hashes(b, ["commerce/group_mq.py", "commerce/flow_service.py", "agentlink_runtime/partner_app.py"])
    b.close()

    print("==== Aliyun suppliers ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(
        SUPPLIER,
        username="root",
        password=PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(s, SUPPLIER_FILES)
    ensure_env(s)
    run(
        s,
        """
set -e
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 4
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for p in 8011 8013 8014; do curl -sk https://127.0.0.1:$p/health; echo; done
""",
    )
    ok_s = verify_hashes(s, ["commerce/group_mq.py", "agentlink_runtime/partner_app.py"])
    s.close()

    if ok_b and ok_s:
        print("SYNC_OK local==servers", flush=True)
        return 0
    print("SYNC_MISMATCH", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
