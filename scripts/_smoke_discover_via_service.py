"""Smoke discover through running buyer systemd env (has ADP URL)."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
CHECK = r"""
# pull env from systemd unit then run tool
cd /opt/agentlink
ENVF=$(systemctl show agentlink-buyer-a -p EnvironmentFiles --value | head -1 | awk '{print $1}')
echo "envfile=$ENVF"
set -a
[ -f "$ENVF" ] && . "$ENVF"
set +a
echo "DISCOVERY=${ACPS_DISCOVERY_URL:-unset}"
/opt/agentlink/.venv/bin/python - <<'PY'
import asyncio, json, os
print('url_set', bool(os.getenv('ACPS_DISCOVERY_URL')))
from commerce.buyer_tools.service import get_buyer_tools

async def main():
    tools = get_buyer_tools()
    out = await tools.discover_suppliers_tool({
        'product_name': '重型脚轮',
        'quantity': 500,
        'query': '脚轮 供应商 agentlink',
        'limit': 5,
        'refresh': True,
    })
    print(json.dumps({
        'ok': out.get('ok'),
        'case_id': out.get('case_id'),
        'source': out.get('source'),
        'n': len(out.get('candidates') or []),
        'ui_form': (out.get('ui_hint') or {}).get('form'),
        'platform_error': out.get('platform_error'),
        'names': [c.get('name') for c in (out.get('candidates') or [])[:3]],
        'ids': [c.get('candidate_id') for c in (out.get('candidates') or [])[:3]],
    }, ensure_ascii=False))

asyncio.run(main())
PY
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    _, stdout, stderr = c.exec_command(CHECK, timeout=180, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR:", err)
    c.close()


if __name__ == "__main__":
    main()
