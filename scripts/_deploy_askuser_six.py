# -*- coding: utf-8 -*-
"""轻量热部署：AskUser 时机 + 供应/物流 Wit 目标驱动（避开全量 tar SCP 断连）。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce/hitl_policy.py",
    "commerce/goal_runtime.py",
    "commerce/choice_actions.py",
    "commerce/chat_buyer_wit.py",
    "commerce/chat_logistics_wit.py",
    "agents/logistics/main.py",
    "docs/design_goal_driven_runtime.md",
]

SUPPLIER_FILES = [
    "commerce/hitl_policy.py",
    "commerce/goal_runtime.py",
    "commerce/choice_actions.py",
    "commerce/chat_supplier_wit.py",
]


def put_host(host: str, files: list[str], *, pem: bool, restart: str) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    sftp = c.open_sftp()
    for rel in files:
        local = ROOT / rel
        if not local.is_file():
            print("SKIP missing", rel, flush=True)
            continue
        remote = f"/opt/agentlink/{rel.replace(chr(92), '/')}"
        parent = str(Path(remote).parent).replace("\\", "/")
        try:
            sftp.stat(parent)
        except OSError:
            _, o, e = c.exec_command(f"mkdir -p {parent}", timeout=20)
            o.channel.recv_exit_status()
        sftp.put(str(local), remote)
        print("put", host, rel, flush=True)
    sftp.close()
    _, o, e = c.exec_command(restart, timeout=120, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace")[-3000:], flush=True)
    c.close()


def remote_smoke_cmd(*, role: str) -> str:
    extra = {
        "buyer": "import commerce.chat_buyer_wit, commerce.chat_logistics_wit; print('wit_buyer_log_ok')",
        "supplier": "import commerce.chat_supplier_wit; print('wit_supplier_ok')",
    }[role]
    return rf"""
set -e
cd /opt/agentlink
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '/opt/agentlink')
from commerce.hitl_policy import should_offer_choices, recommend_first, choices_from_blockers
from commerce.goal_runtime import blocker, with_runtime_meta

assert not should_offer_choices(branch_count=1)
assert should_offer_choices(branch_count=2)
assert should_offer_choices(ambiguous=True)
assert not should_offer_choices(gate='approve_plan', branch_count=1)
bl_sup = [blocker(code='MISSING_VOLUME', message='缺体积', holder='supplier', repair_tool='flow.backfill_specs')]
assert not should_offer_choices(blockers=bl_sup, branch_count=0)
assert choices_from_blockers(bl_sup) is None
bl_h = [blocker(code='MULTI', message='多笔', holder='buyer_human', repair_tool='ui.offer_choices')]
w = choices_from_blockers(bl_h)
assert w and '推荐' in (w['choices'][0].get('label') or '')
ch = recommend_first([{{'id':'a','label':'A'}}, {{'id':'b','label':'B','primary':True}}])
assert ch[0]['id']=='b' and '推荐' in ch[0]['label']
out = with_runtime_meta({{'x':1}}, goal='承运', blockers=bl_sup, next_actions=['flow.backfill_specs'])
assert out.get('blockers') and out['blockers'][0]['repair_tool']=='flow.backfill_specs'
{extra}
print('ASKUSER_SMOKE_PASS')
PY
"""


def run_smoke(host: str, *, pem: bool, role: str) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    _, o, e = c.exec_command(remote_smoke_cmd(role=role), timeout=90, get_pty=True)
    text = (o.read() + e.read()).decode("utf-8", "replace")
    print(f"==== smoke {host} ====\n{text[-4000:]}", flush=True)
    if "ASKUSER_SMOKE_PASS" not in text:
        raise SystemExit(f"smoke failed on {host}")
    c.close()


def main() -> None:
    put_host(
        "81.70.46.119",
        BUYER_FILES,
        pem=True,
        restart=(
            "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
            "sleep 5; systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics"
        ),
    )
    put_host(
        "39.105.20.113",
        SUPPLIER_FILES,
        pem=False,
        restart=(
            "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c "
            "agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp 2>/dev/null; "
            "sleep 4; systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c"
        ),
    )
    run_smoke("81.70.46.119", pem=True, role="buyer")
    run_smoke("39.105.20.113", pem=False, role="supplier")
    print("DEPLOY_ASKUSER_SIX_DONE", flush=True)


if __name__ == "__main__":
    main()
