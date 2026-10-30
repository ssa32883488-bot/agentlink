# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

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
    _, o, _ = c.exec_command(
        "cd /opt/agentlink && .venv/bin/python -c \""
        "import json;from pathlib import Path;"
        "d=json.loads(Path('data/procurement_cases_buyer-b.json').read_text(encoding='utf-8'));"
        "case=d['cases']['case-7d77f9af'];"
        "print(json.dumps({'brief':case.get('brief'),'rfq':case.get('rfq_batch') or case.get('last_rfq_batch')},"
        "ensure_ascii=False,indent=2)[:4000])"
        "\"",
        timeout=40,
        get_pty=True,
    )
    print(o.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
