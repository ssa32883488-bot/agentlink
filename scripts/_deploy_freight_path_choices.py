# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
FILES = [
    "commerce/choice_actions.py",
    "commerce/hitl_gate.py",
    "commerce/flow_service.py",
    "commerce/chat_buyer_wit.py",
]


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
    for rel in FILES:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()
    _, o, e = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 5; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b; "
        "cd /opt/agentlink && .venv/bin/python - <<'PY'\n"
        "from commerce.choice_actions import post_freight_path_choices\n"
        "w=post_freight_path_choices(case_id='case-x', supplier_agent_id='supplier-a')\n"
        "labels=[c['label'] for c in w['choices']]\n"
        "print(labels)\n"
        "assert '自己联系物流' in labels and '请对方联系物流' in labels\n"
        "print('FREIGHT_PATH_OK')\n"
        "PY",
        timeout=60,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"), flush=True)
    c.close()


if __name__ == "__main__":
    main()
