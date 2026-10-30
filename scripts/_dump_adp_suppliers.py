"""Find which queries surface supplier AICs on Wutong ADP."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r"""
set -a; . /opt/agentlink/.env; set +a
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import httpx, os
base=os.environ['ACPS_DISCOVERY_URL'].rstrip('/')
url=base+'/acps-adp-v2/discover'
needles=('NH4J42','SHDUXP','8R39K3')
queries=[
 '采联供应商智能体A',
 '采联供应商智能体B',
 '采联供应商智能体C',
 '采联供应商',
 'agentlink.supplier',
 'scarce-quote',
 'price-first supplier',
 '39.105.20.113:8011',
 'NH4J42',
]
for q in queries:
    r=httpx.post(url,json={'type':'explicit','query':q,'limit':15},timeout=35)
    d=r.json(); res=d.get('result') or {}; m=res.get('acsMap') or {}
    hits=[(acs.get('name'),aic[-18:], ((acs.get('endPoints') or [{}])[0] or {}).get('url',''))
           for aic,acs in m.items() if any(n in aic for n in needles) or '供应商' in str(acs.get('name') or '')]
    print(f'Q={q!r} status={r.status_code} map={len(m)} hits={len(hits)}')
    for h in hits[:6]:
        print(' ', h)
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
    _, stdout, _ = c.exec_command(REMOTE, timeout=300, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
