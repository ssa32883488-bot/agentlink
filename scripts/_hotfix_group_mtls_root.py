# -*- coding: utf-8 -*-
"""热修：Group mTLS 证书根路径指错（commerce/ 而非 agentlink/），并验证 open_group。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
REL = "commerce/_legacy/group_mq.py"


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd[:140], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-2200:], flush=True)
    return out


def put(c: paramiko.SSHClient) -> None:
    remote = f"/opt/agentlink/{REL}"
    with SCPClient(c.get_transport()) as scp:
        run(c, f"mkdir -p {Path(remote).parent.as_posix()}")
        print("put", REL, flush=True)
        scp.put(str(ROOT / REL), remote)
        run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{REL} 2>/dev/null || true")


def main() -> None:
    cb = connect("buyer")
    put(cb)
    # 确保 MQ 开关；不在共享 .env 写死 AIP_CLIENT（六体共用会串证书）
    run(
        cb,
        "grep -q '^V2_TRY_GROUP_MQ=' /opt/agentlink/.env 2>/dev/null || echo 'V2_TRY_GROUP_MQ=1' >> /opt/agentlink/.env; "
        "grep -q '^ACPS_GROUP_IDENTITY_BINDING=' /opt/agentlink/.env 2>/dev/null || echo 'ACPS_GROUP_IDENTITY_BINDING=1' >> /opt/agentlink/.env; "
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; sleep 2; "
        "systemctl is-active agentlink-buyer-a agentlink-logistics",
    )
    run(
        cb,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "from commerce._legacy import group_mq as g\n"
        "print('ROOT', g._ROOT)\n"
        "print('paths', g._cert_paths('buyer-a'))\n"
        "print('paths_logistics', g._cert_paths('logistics'))\n"
        "ctx=g.build_agent_ssl_context('buyer-a')\n"
        "print('ssl_ok', type(ctx).__name__)\n"
        "import asyncio\n"
        "async def main():\n"
        "  try:\n"
        "    rec=await asyncio.wait_for(g.open_group(\n"
        "      leader_aic=__import__('os').getenv('BUYER_A_AIC','buyer-a-local-aic'),\n"
        "      leader_agent_id='buyer-a',\n"
        "      member_agent_ids=['supplier-b','logistics'],\n"
        "      invite=True,\n"
        "    ), timeout=45)\n"
        "    print('OPEN_OK', getattr(rec,'session_id',None) or rec)\n"
        "    print('members', getattr(rec,'members',None))\n"
        "    print('invite_errors', getattr(rec,'invite_errors',None))\n"
        "  except Exception as e:\n"
        "    print('OPEN_FAIL', type(e).__name__, str(e)[:300])\n"
        "asyncio.run(main())\n"
        "PY",
    )
    cb.close()

    cs = connect("supplier")
    put(cs)
    run(
        cs,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 2; "
        "systemctl is-active agentlink-supplier-b; "
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "from commerce._legacy import group_mq as g\n"
        "print('ROOT', g._ROOT)\n"
        "print('paths', g._cert_paths('supplier-b'))\n"
        "print('ssl', type(g.build_agent_ssl_context('supplier-b')).__name__)\n"
        "PY",
    )
    cs.close()
    print("HOTFIX_GROUP_MTLS_ROOT_DONE", flush=True)


if __name__ == "__main__":
    main()
