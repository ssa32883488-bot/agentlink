# -*- coding: utf-8 -*-
"""热修：国标 Group 邀请跨云自签 HTTPS + 确认 AIC/证书已生效。"""
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
    print("$", cmd[:150], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-2600:], flush=True)
    return out


def main() -> None:
    cb = connect("buyer")
    with SCPClient(cb.get_transport()) as scp:
        remote = f"/opt/agentlink/{REL}"
        run(cb, f"mkdir -p {Path(remote).parent.as_posix()}")
        print("put", REL, flush=True)
        scp.put(str(ROOT / REL), remote)
        run(cb, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{REL} 2>/dev/null || true")
    # 确保 AIP_SSL_INSECURE 与 AIC
    run(
        cb,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "from pathlib import Path\n"
        "p=Path('.env'); lines=p.read_text(encoding='utf-8').splitlines() if p.exists() else []\n"
        "kv={'AIP_SSL_INSECURE':'1','V2_TRY_GROUP_MQ':'1','ACPS_GROUP_IDENTITY_BINDING':'1',\n"
        " 'BUYER_A_AIC':'1.2.156.3088.1.BUPT.2HY2P9.IFL6BJ.MWEDJS.0GUC',\n"
        " 'BUYER_B_AIC':'1.2.156.3088.1.BUPT.2HY2P9.L18AT6.DR2I98.0IWJ',\n"
        " 'LOGISTICS_AIC':'1.2.156.3088.1.BUPT.2HY2P9.JOBNF9.39B1TM.0ALR',\n"
        " 'SUPPLIER_A_AIC':'1.2.156.3088.1.BUPT.2HY2P9.WP4OOG.AE0C7A.1CHP',\n"
        " 'SUPPLIER_B_AIC':'1.2.156.3088.1.BUPT.2HY2P9.6CW2XR.2UXYPG.1CQG',\n"
        " 'SUPPLIER_C_AIC':'1.2.156.3088.1.BUPT.2HY2P9.1VQMIO.SY0GFP.09NH'}\n"
        "out=[]; seen=set()\n"
        "for line in lines:\n"
        "  if not line.strip() or line.lstrip().startswith('#') or '=' not in line:\n"
        "    out.append(line); continue\n"
        "  k=line.split('=',1)[0].strip()\n"
        "  if k in kv: out.append(f'{k}={kv[k]}'); seen.add(k)\n"
        "  else: out.append(line)\n"
        "for k,v in kv.items():\n"
        "  if k not in seen: out.append(f'{k}={v}')\n"
        "p.write_text('\\n'.join(out)+'\\n', encoding='utf-8'); print('ok', sorted(kv))\n"
        "PY",
    )
    run(
        cb,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; sleep 2; "
        "systemctl is-active agentlink-buyer-a",
    )
    cs = connect("supplier")
    with SCPClient(cs.get_transport()) as scp:
        remote = f"/opt/agentlink/{REL}"
        run(cs, f"mkdir -p {Path(remote).parent.as_posix()}")
        scp.put(str(ROOT / REL), remote)
        run(cs, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{REL} 2>/dev/null || true")
    run(
        cs,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "from pathlib import Path\n"
        "p=Path('.env'); lines=p.read_text(encoding='utf-8').splitlines() if p.exists() else []\n"
        "kv={'AIP_SSL_INSECURE':'1','ACPS_GROUP_IDENTITY_BINDING':'1',\n"
        " 'BUYER_A_AIC':'1.2.156.3088.1.BUPT.2HY2P9.IFL6BJ.MWEDJS.0GUC',\n"
        " 'LOGISTICS_AIC':'1.2.156.3088.1.BUPT.2HY2P9.JOBNF9.39B1TM.0ALR',\n"
        " 'SUPPLIER_A_AIC':'1.2.156.3088.1.BUPT.2HY2P9.WP4OOG.AE0C7A.1CHP',\n"
        " 'SUPPLIER_B_AIC':'1.2.156.3088.1.BUPT.2HY2P9.6CW2XR.2UXYPG.1CQG',\n"
        " 'SUPPLIER_C_AIC':'1.2.156.3088.1.BUPT.2HY2P9.1VQMIO.SY0GFP.09NH'}\n"
        "out=[]; seen=set()\n"
        "for line in lines:\n"
        "  if not line.strip() or line.lstrip().startswith('#') or '=' not in line:\n"
        "    out.append(line); continue\n"
        "  k=line.split('=',1)[0].strip()\n"
        "  if k in kv: out.append(f'{k}={kv[k]}'); seen.add(k)\n"
        "  else: out.append(line)\n"
        "for k,v in kv.items():\n"
        "  if k not in seen: out.append(f'{k}={v}')\n"
        "p.write_text('\\n'.join(out)+'\\n', encoding='utf-8'); print('ok')\n"
        "PY",
    )
    run(
        cs,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 2; "
        "systemctl is-active agentlink-supplier-b; "
        "curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8013/group/join -X POST -H 'Content-Type: application/json' -d '{}' ; echo",
    )
    cs.close()

    run(
        cb,
        "cd /opt/agentlink && set -a && . ./.env && set +a && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "import asyncio, os\n"
        "from commerce._legacy import group_mq as g\n"
        "async def main():\n"
        "  rec=await asyncio.wait_for(g.open_group(\n"
        "    leader_aic=os.environ['BUYER_A_AIC'], leader_agent_id='buyer-a',\n"
        "    member_agent_ids=['supplier-b','supplier-c','logistics'], invite=True),\n"
        "    timeout=90)\n"
        "  print('OPEN_OK', getattr(rec,'session_id',None))\n"
        "  rows=getattr(rec,'members',None) or getattr(rec,'member_rows',None)\n"
        "  print('members', rows)\n"
        "  print('invite_errors', getattr(rec,'invite_errors',None))\n"
        "asyncio.run(main())\n"
        "PY",
    )
    cb.close()
    print("HOTFIX_GROUP_INVITE_SSL_DONE", flush=True)


if __name__ == "__main__":
    main()
