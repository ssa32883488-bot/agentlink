# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce/goal_runtime.py",
    "commerce/chat_buyer_wit.py",
    "commerce/flow_service.py",
    "commerce/buyer_tools/service.py",
    "commerce/choice_actions.py",
    "docs/design_goal_driven_runtime.md",
]


def put_host(host: str, *, pem: bool, restart: str) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    sftp = c.open_sftp()
    for rel in FILES:
        local = ROOT / rel
        if not local.is_file():
            continue
        remote = f"/opt/agentlink/{rel}"
        # ensure parent
        try:
            sftp.stat(str(Path(remote).parent).replace("\\", "/"))
        except OSError:
            c.exec_command(f"mkdir -p {Path(remote).parent.as_posix()}", timeout=20)
        sftp.put(str(local), remote)
        print("put", host, rel, flush=True)
    sftp.close()
    _, o, e = c.exec_command(restart, timeout=90, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()


def smoke_tencent() -> None:
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
    cmd = r"""
set -e
/opt/agentlink/.venv/bin/python - <<'PY'
import sys
sys.path.insert(0,'/opt/agentlink')
from commerce import goal_runtime as gr

# blockers when no volume
bl = gr.shipping_blockers_from_mass({'weight_kg': 10})
assert any(b['code']=='MISSING_VOLUME' for b in bl), bl
assert bl[0]['repair_tool']=='flow.backfill_specs'

# with_runtime_meta injects reminder
out = gr.with_runtime_meta({'x':1}, goal='承运', blockers=bl)
assert 'system_reminder' in out and 'MISSING_VOLUME' in out['system_reminder']
assert 'flow.backfill_specs' in out['next_actions']

# backfill from catalog (no ticket)
import asyncio
async def t():
    r = await gr.backfill_specs('buyer-a', case_id=None, order_ticket_id=None, ask_supplier=False)
    # without case/sku may still have blockers — just ensure API shape
    assert 'blockers' in r and 'ok' in r
    # direct patch via seat catalog path
    from commerce.seat_catalog import product_physical_specs
    specs = product_physical_specs('RM-CASTER-300', qty=500)
    assert specs.get('volume_m3') and specs.get('weight_kg')
    print('specs500', specs.get('volume_m3'), specs.get('weight_kg'))
    print('PASS')
asyncio.run(t())
PY
"""
    _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()


def main() -> None:
    put_host(
        "81.70.46.119",
        pem=True,
        restart=(
            "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
            "sleep 4; systemctl is-active agentlink-buyer-a"
        ),
    )
    # aliyun: optional copy of goal_runtime for shared libs; suppliers don't need wit
    put_host(
        "39.105.20.113",
        pem=False,
        restart="echo aliyun_files_ok",
    )
    smoke_tencent()
    print("DEPLOY_GOAL_RUNTIME_DONE", flush=True)


if __name__ == "__main__":
    main()
