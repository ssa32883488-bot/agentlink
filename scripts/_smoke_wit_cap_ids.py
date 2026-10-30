"""Inspect Wit capability ids on remote buyer."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
CHECK = r"""
cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'
from commerce.chat_buyer_wit import _build_capabilities
caps = _build_capabilities(None)
for c in caps:
    attrs = {k: getattr(c, k, None) for k in dir(c) if 'cap' in k.lower() or k in ('id', 'name', '__name__', '__doc__')}
    meta = None
    for k in ('__wit_capability__', '__capability__', '_capability', 'capability', '__wrapped__'):
        if hasattr(c, k):
            meta = getattr(c, k)
            break
    print('---', getattr(c, '__name__', '?'))
    print('  attrs', {k:v for k,v in attrs.items() if v is not None and not callable(v)})
    if meta is not None:
        print('  meta', meta)
        print('  meta_dir', [x for x in dir(meta) if not x.startswith('_')][:20])
    # inspect closure / decorator annotations
    print('  annotations', getattr(c, '__annotations__', None))
    print('  dict_keys', list(getattr(c, '__dict__', {}).keys())[:30])
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
    _, stdout, _ = c.exec_command(CHECK, timeout=60, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
