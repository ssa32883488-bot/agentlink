# -*- coding: utf-8 -*-
"""Deploy chat_buyer_wit brace fix; restart buyers; verify import + tickets API."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c.open_sftp()
    sftp.put(str(ROOT / "commerce/chat_buyer_wit.py"), "/opt/agentlink/commerce/chat_buyer_wit.py")
    sftp.close()
    print("put chat_buyer_wit.py", flush=True)
    _, o, e = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 4; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b; "
        "set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a; "
        "cd /opt/agentlink && .venv/bin/python - <<'PY'\n"
        "from commerce.chat_buyer_wit import INSTRUCTIONS\n"
        "assert '采联·采购商A' in INSTRUCTIONS\n"
        "print('IMPORT_OK', len(INSTRUCTIONS))\n"
        "PY\n"
        "curl -sk -o /tmp/tix.json -w 'tickets_http=%{http_code}\\n' https://127.0.0.1:8010/api/erp/tickets; "
        "python3 -c \"import json;d=json.load(open('/tmp/tix.json'));print('tickets_n',len(d.get('items') or []))\" 2>/dev/null || head -c 200 /tmp/tix.json; echo",
        timeout=90,
        get_pty=True,
    )
    out = (o.read() + e.read()).decode("utf-8", "replace")
    sys.stdout.write(out + "\n")
    c.close()
    if "IMPORT_OK" not in out or "active" not in out:
        raise SystemExit(1)
    print("FIX_BUYER_CRASH_DONE", flush=True)


if __name__ == "__main__":
    main()
