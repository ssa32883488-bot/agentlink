# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import paramiko

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(
        r"""
systemctl is-active agentlink-supplier-a-erp
systemctl status agentlink-supplier-a-erp --no-pager -l | head -25
tail -n 40 /var/log/agentlink/supplier-a-erp.log 2>/dev/null || journalctl -u agentlink-supplier-a-erp -n 40 --no-pager
cd /opt/agentlink
.venv/bin/python - <<'PY'
from commerce.chat_supplier_wit import configure, _promotions_payload
configure(agent_id='supplier-a')
print(_promotions_payload())
configure(agent_id='supplier-b')
print(_promotions_payload())
configure(agent_id='supplier-c')
print(_promotions_payload())
PY
curl -sS -m 5 -w '\nHTTP:%{http_code}\n' http://127.0.0.1:18011/api/erp/promotions | head -c 500; echo
""",
        timeout=60,
        get_pty=True,
    )
    sys.stdout.buffer.write((o.read() + e.read()) + b"\n")
    sys.stdout.buffer.flush()
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
