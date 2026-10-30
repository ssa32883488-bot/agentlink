"""Install kafka-python into /opt/agentlink/.venv on both hosts."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

HOSTS = [
    {"host": "81.70.46.119", "auth": "key", "role": "buyer"},
    {
        "host": "39.105.20.113",
        "auth": "password",
        "password": os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"),
        "role": "supplier",
    },
]

INSTALL = r"""
set -e
PY=/opt/agentlink/.venv/bin/python
cd /opt/agentlink
echo "python=$($PY -V)"
# prefer ensurepip + pip
$PY -m ensurepip --upgrade 2>/dev/null || true
$PY -m pip install -q --upgrade pip 2>/dev/null || true
if $PY -m pip install -q 'kafka-python>=2.0.2'; then
  echo pip_ok
elif command -v uv >/dev/null 2>&1; then
  uv pip install --python "$PY" -q 'kafka-python>=2.0.2'
  echo uv_ok
else
  # last resort: download wheel via curl and pip install path
  mkdir -p /tmp/ampwheels
  $PY - <<'PY'
import urllib.request, sys
url='https://pypi.org/simple/kafka-python/'
print('fallback fetch via pip unavailable')
sys.exit(2)
PY
fi
$PY -c "import kafka; print('kafka_import_ok', getattr(kafka,'__version__', '?'))"
set -a; . /opt/agentlink/.env; set +a
$PY - <<'PY'
import os
import commerce.amp_log as m
m._kafka_failed=False
m._kafka_producer=None
aic=os.getenv('BUYER_A_AIC') or os.getenv('SUPPLIER_A_AIC') or 'test-aic'
peer=os.getenv('SUPPLIER_A_AIC') or os.getenv('BUYER_A_AIC') or 'peer-aic'
direction='send' if os.getenv('BUYER_A_AIC') else 'receive'
out=m.record_access(task_id='task-amp-kafka-live', local_aic=aic, peer_aic=peer,
                    direction=direction, endpoint='https://amp.smoke/rpc', status='ok')
print('producer', m._kafka_producer is not None, 'failed', m._kafka_failed)
print('corr', out['access'].get('correlationId'), 'evt', out['message']['body']['eventType'],
      'mid', out['message']['body']['messageId'])
PY
"""


def connect(spec: dict) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if spec["auth"] == "key":
        c.connect(
            spec["host"],
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
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


def main() -> None:
    for spec in HOSTS:
        print(f"\n==== install kafka {spec['role']} {spec['host']} ====")
        c = connect(spec)
        _, stdout, stderr = c.exec_command(INSTALL, timeout=300, get_pty=True)
        print(stdout.read().decode("utf-8", errors="replace")[-5000:])
        err = stderr.read().decode("utf-8", errors="replace")
        if err.strip():
            print(err[-1000:], file=sys.stderr)
        c.close()


if __name__ == "__main__":
    main()
