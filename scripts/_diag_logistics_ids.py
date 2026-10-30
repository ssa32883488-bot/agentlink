# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    _i, o, e = c.exec_command(
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "d=json.loads(Path('data/v2_orders/orders.json').read_text())\n"
        "for k,v in (d.get('logistics') or {}).items():\n"
        "  print('KEY', k)\n"
        "  print('  logistics_id', v.get('logistics_id'), 'order_id', v.get('order_id'), 'title', (v.get('title') or '')[:40])\n"
        "  print('  buyer_ack', v.get('buyer_ack'), 'logistics_ack', v.get('logistics_ack'), 'effective', v.get('effective'))\n"
        "PY",
        timeout=30,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
