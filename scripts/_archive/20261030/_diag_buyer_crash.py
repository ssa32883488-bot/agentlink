# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r"""
set -e
echo "=== status ==="
systemctl is-active agentlink-buyer-a || true
systemctl status agentlink-buyer-a --no-pager -l | head -25 || true
echo "=== unit ExecStart ==="
grep -E 'ExecStart|Environment|WorkingDirectory' /etc/systemd/system/agentlink-buyer-a.service
echo "=== app log ==="
tail -100 /var/log/agentlink/buyer-a.log 2>/dev/null || echo no_app_log
echo "=== import test ==="
set -a
. /opt/agentlink/.env
. /etc/agentlink/buyer-a.env
set +a
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import traceback
try:
    from agents.buyer_a import main as m
    print("import_ok", getattr(m, "app", None))
except Exception:
    traceback.print_exc()
try:
    import commerce.procurement_case as pc
    print("STATE_FOCUS", "DISCOVERING" in getattr(pc, "STATE_FOCUS", {}))
    print("describe", callable(getattr(pc, "describe_state_focus", None)))
except Exception:
    traceback.print_exc()
try:
    import commerce.chat_buyer_wit as w
    print("wit_ok", "世界模型" in (w.INSTRUCTIONS or ""))
except Exception:
    traceback.print_exc()
PY
"""


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
    _, o, e = c.exec_command(REMOTE, timeout=60)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
