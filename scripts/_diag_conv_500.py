# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _i, o, e = c.exec_command(cmd, timeout=60)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def main() -> None:
    c = connect()
    print("=== hit conversations + tail log ===")
    print(run(c, "curl -sk -m 8 https://127.0.0.1:8010/api/erp/conversations >/tmp/conv.out 2>/tmp/conv.err; echo OUT:; head -c 400 /tmp/conv.out; echo; echo ERR:; cat /tmp/conv.err; echo; tail -n 80 /var/log/agentlink/buyer-a.log"))
    print("=== local import traceback ===")
    print(
        run(
            c,
            r"""cd /opt/agentlink && AGENTLINK_RUNTIME=v2 /opt/agentlink/.venv/bin/python - <<'PY'
from commerce_v2.routes import mount_v2_buyer
# call conversations handler internals
from commerce_v2 import thread_store, case_store
agent_id='buyer-a'
tid=thread_store.active_thread_id(agent_id)
print('tid', tid)
tid, msgs = thread_store.list_messages(agent_id, tid, limit=80)
print('msgs', len(msgs))
th = thread_store.get_thread(agent_id, tid)
print('th case', (th or {}).get('case_id'))
case = case_store.get_case(agent_id, th.get('case_id')) if th and th.get('case_id') else None
print('case', (case or {}).get('case_id'), (case or {}).get('state'))
print('pending', bool((case or {}).get('pending_choices')))
print('hitl', (case or {}).get('hitl_pending'))
if case and (case.get('hitl_pending') or {}).get('gate')=='confirm_shortlist' and case.get('candidates'):
    from commerce_v2.widgets import shortlist_widget
    try:
        w=shortlist_widget(case)
        print('widget ok', type(w))
    except Exception as e:
        print('widget fail', e)
PY"""
        )
    )
    c.close()


if __name__ == "__main__":
    main()
