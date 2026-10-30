"""Deploy AMP Kafka Access+Message reporting to buyer + supplier hosts."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

BUYER = {"host": "81.70.46.119", "user": "root", "auth": "key", "role": "buyer"}
SUPPLIER = {
    "host": "39.105.20.113",
    "user": "root",
    "auth": "password",
    "password": os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"),
    "role": "supplier",
}

FILES = [
    ("commerce/amp_log.py", "/opt/agentlink/commerce/amp_log.py"),
    ("agentlink_runtime/aip_client_util.py", "/opt/agentlink/agentlink_runtime/aip_client_util.py"),
    ("agentlink_runtime/partner_app.py", "/opt/agentlink/agentlink_runtime/partner_app.py"),
]

ENV_LINES = {
    "AMP_KAFKA_ENABLED": "1",
    "AMP_KAFKA_BOOTSTRAP": "wt.ioa.pub:19092",
    "AMP_ACCESS_TOPIC": "amp.access",
    "AMP_MESSAGE_TOPIC": "amp.message",
    "AMP_KAFKA_FLUSH": "1",
}


def connect(spec: dict) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if spec["auth"] == "key":
        c.connect(
            spec["host"],
            username=spec["user"],
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    else:
        c.connect(
            spec["host"],
            username=spec["user"],
            password=spec["password"],
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> str:
    print(f"$ {cmd[:160]}...")
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(out[-3500:])
    if err.strip():
        print(err[-800:], file=sys.stderr)
    return out


def upsert_env(c: paramiko.SSHClient) -> None:
    # write a small remote python to merge env keys
    py = r"""
from pathlib import Path
p=Path('/opt/agentlink/.env')
text=p.read_text(encoding='utf-8') if p.exists() else ''
lines=text.splitlines()
keys={
 'AMP_KAFKA_ENABLED':'1',
 'AMP_KAFKA_BOOTSTRAP':'wt.ioa.pub:19092',
 'AMP_ACCESS_TOPIC':'amp.access',
 'AMP_MESSAGE_TOPIC':'amp.message',
 'AMP_KAFKA_FLUSH':'1',
}
keep=[]
seen=set()
for line in lines:
    if not line.strip() or line.strip().startswith('#') or '=' not in line:
        keep.append(line); continue
    k=line.split('=',1)[0].strip()
    if k in keys:
        keep.append(f'{k}={keys[k]}'); seen.add(k)
    else:
        keep.append(line)
for k,v in keys.items():
    if k not in seen:
        keep.append(f'{k}={v}')
p.write_text('\n'.join(keep).rstrip()+'\n', encoding='utf-8')
print('env amp keys ok')
"""
    sftp = c.open_sftp()
    with sftp.file("/tmp/amp_env.py", "w") as f:
        f.write(py)
    sftp.close()
    run(c, "/opt/agentlink/.venv/bin/python /tmp/amp_env.py")


def deploy(spec: dict) -> None:
    print(f"\n==== AMP deploy {spec['role']} {spec['host']} ====")
    c = connect(spec)
    with SCPClient(c.get_transport()) as scp:
        for local, remote in FILES:
            scp.put(str(ROOT / local), remote)
            print("put", local)
    upsert_env(c)
    run(
        c,
        "/opt/agentlink/.venv/bin/pip install -q 'kafka-python>=2.0.2' || "
        "/opt/agentlink/.venv/bin/uv pip install -q 'kafka-python>=2.0.2'",
        timeout=240,
    )
    if spec["role"] == "buyer":
        svcs = "agentlink-buyer-a agentlink-buyer-b agentlink-logistics"
    else:
        svcs = "agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c"
    run(c, f"systemctl restart {svcs}; sleep 3; systemctl is-active {svcs}")
    # smoke emit
    run(
        c,
        r"""
cd /opt/agentlink
set -a; . ./.env; set +a
/opt/agentlink/.venv/bin/python - <<'PY'
import os, json
from commerce.amp_log import record_access
aic=os.getenv('BUYER_A_AIC') or os.getenv('SUPPLIER_A_AIC') or 'test-aic'
peer=os.getenv('SUPPLIER_A_AIC') or os.getenv('BUYER_A_AIC') or 'peer-aic'
out=record_access(task_id='task-amp-smoke-001', local_aic=aic, peer_aic=peer,
                  direction='send' if 'BUYER_A_AIC' in open('/opt/agentlink/.env').read() else 'receive',
                  endpoint='https://smoke.local/rpc', status='awaiting-completion',
                  extra={'schema':'agentlink.amp.smoke'})
print('access_log_type', out['access']['log_type'], 'corr', out['access'].get('correlationId'))
print('message_event', out['message']['body'].get('eventType'), 'msgId', out['message']['body'].get('messageId'))
print('kafka_bootstrap', os.getenv('AMP_KAFKA_BOOTSTRAP'))
# show tail
from pathlib import Path
for name in ('amp_access.jsonl','amp_message.jsonl'):
  p=Path('logs')/name
  if p.exists():
    print(name, 'lines', len(p.read_text(encoding='utf-8').splitlines()))
PY
""",
        timeout=60,
    )
    c.close()


def main() -> None:
    targets = sys.argv[1:] or ["buyer", "supplier"]
    if "buyer" in targets:
        deploy(BUYER)
    if "supplier" in targets:
        deploy(SUPPLIER)


if __name__ == "__main__":
    main()
