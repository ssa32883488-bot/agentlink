"""Overnight competition harden: deploy buyer+supplier, sync AMP, run evidence."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"

BUYER_FILES = [
    "commerce/hitl_gate.py",
    "commerce/amp_metrics.py",
    "commerce/amp_log.py",
    "commerce/discovery.py",
    "commerce/flow_service.py",
    "commerce/flow_routes.py",
    "commerce/chat_buyer_wit.py",
    "agentlink_runtime/aip_client_util.py",
    "agentlink_runtime/partner_app.py",
    "ui/static/app.js",
    "ui/static/styles.css",
    "scripts/demo_acps_evidence.py",
    ".env.example",
]

SUPPLIER_FILES = [
    "commerce/amp_log.py",
    "agentlink_runtime/partner_app.py",
    "agentlink_runtime/aip_client_util.py",
]


def connect(host: str, *, password: str | None = None) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        c.connect(host, username="root", password=password, timeout=40, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            host,
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=40,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def put_files(c: paramiko.SSHClient, files: list[str]) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in files:
            local = ROOT / rel
            if not local.is_file():
                print("skip missing", rel)
                continue
            remote = f"/opt/agentlink/{rel.replace(chr(92), '/')}"
            # ensure parent
            parent = str(Path(remote).parent).replace("\\", "/")
            c.exec_command(f"mkdir -p {parent}")
            scp.put(str(local), remote)
            print("put", host_label(c), rel)


def host_label(c: paramiko.SSHClient) -> str:
    return c.get_transport().getpeername()[0] if c.get_transport() else "?"


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> str:
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-5000:])
    return out


def main() -> None:
    buyer = connect(BUYER)
    supplier = connect(SUPPLIER, password=os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"))

    print("==== deploy buyer ====")
    put_files(buyer, BUYER_FILES)
    run(
        buyer,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics agentlink-ui-buyer; "
        "sleep 5; systemctl is-active agentlink-buyer-a agentlink-ui-buyer",
    )

    print("==== deploy supplier + AMP env ====")
    put_files(supplier, SUPPLIER_FILES)
    run(
        supplier,
        r"""
set -e
cd /opt/agentlink
# ensure AMP kafka vars present (idempotent append if missing)
if ! grep -q '^AMP_KAFKA_ENABLED=' .env 2>/dev/null; then
  cat >> .env <<'EOF'
AMP_KAFKA_ENABLED=1
AMP_KAFKA_BOOTSTRAP=wt.ioa.pub:19092
AMP_ACCESS_TOPIC=amp.access
AMP_MESSAGE_TOPIC=amp.message
AMP_KAFKA_FLUSH=1
EOF
  echo appended_amp_env
else
  echo amp_env_present
  grep -E '^AMP_' .env | head -10
fi
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 5
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
""",
    )

    print("==== evidence on buyer ====")
    run(
        buyer,
        "cd /opt/agentlink && .venv/bin/python scripts/demo_acps_evidence.py; "
        "echo EXIT:$?; "
        "test -f docs/evidence/latest_pair.json && head -c 800 docs/evidence/latest_pair.json; echo",
        timeout=240,
    )

    print("==== bilateral AMP sample (supplier tail) ====")
    run(
        supplier,
        r"""
cd /opt/agentlink
python3 - <<'PY'
import json
from pathlib import Path
p=Path('logs/amp_message.jsonl')
if not p.exists():
  print('no supplier amp_message yet')
else:
  lines=p.read_text(encoding='utf-8').splitlines()[-8:]
  for line in lines:
    r=json.loads(line)
    b=r.get('body') or {}
    print('corr', r.get('correlationId') or r.get('correlation_id'),
          'evt', b.get('eventType'), 'mid', b.get('messageId'), 'op', b.get('operationName'))
PY
""",
    )
    buyer.close()
    supplier.close()
    print("OVERNIGHT_DEPLOY_DONE")


if __name__ == "__main__":
    main()
