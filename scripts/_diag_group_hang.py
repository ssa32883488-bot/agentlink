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
    cmd = r"""
cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'
import json
from pathlib import Path
from commerce_v2 import case_store
# find case-62d58b55
p=Path('data/v2_cases/buyer-a.json')
d=json.loads(p.read_text())
cases=d.get('cases') or {}
for cid,c in cases.items():
  if '62d58b55' in cid or c.get('state') in ('GROUP_BIDDING','GROUP_DECIDE'):
    room=c.get('group_room') or {}
    print('CASE', cid, 'state', c.get('state'), 'msgs', len(room.get('messages') or []), 'ticker', len(room.get('ticker') or []), 'status', room.get('status'), 'transport', room.get('transport'))
    for t in (room.get('ticker') or [])[-6:]:
      print(' T', t.get('kind'), t.get('text','')[:80])
    for m in (room.get('messages') or [])[-4:]:
      print(' M', m.get('role'), str(m.get('content') or '')[:80])
print('--- recent buyer-a log ---')
PY
tail -n 40 /var/log/agentlink/buyer-a.log
"""
    _i, o, e = c.exec_command(cmd, timeout=60)
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
