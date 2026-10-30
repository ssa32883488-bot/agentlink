# -*- coding: utf-8 -*-
"""写入各智能体 AIC（取自 agent-cert CN）并验证国标 Group 开群。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

# 证书 CN（与 openssl subject 一致；Group/AMQP 身份须对齐证书）
AICS = {
    "BUYER_A_AIC": "1.2.156.3088.1.BUPT.2HY2P9.IFL6BJ.MWEDJS.0GUC",
    "BUYER_B_AIC": "1.2.156.3088.1.BUPT.2HY2P9.L18AT6.DR2I98.0IWJ",
    "LOGISTICS_AIC": "1.2.156.3088.1.BUPT.2HY2P9.JOBNF9.39B1TM.0ALR",
    "SUPPLIER_A_AIC": "1.2.156.3088.1.BUPT.2HY2P9.WP4OOG.AE0C7A.1CHP",
    "SUPPLIER_B_AIC": "1.2.156.3088.1.BUPT.2HY2P9.6CW2XR.2UXYPG.1CQG",
    "SUPPLIER_C_AIC": "1.2.156.3088.1.BUPT.2HY2P9.1VQMIO.SY0GFP.09NH",
}

EXTRA = {
    "V2_TRY_GROUP_MQ": "1",
    "ACPS_GROUP_IDENTITY_BINDING": "1",
    "ACPS_MQ_HOST": "wt.ioa.pub",
    "ACPS_MQ_PORT": "5671",
    "ACPS_MQ_VHOST": "acps",
    "ACPS_MQ_AUTH_URL": "https://wt.ioa.pub/mq-auth",
}


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
    print("$", cmd[:160], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-2400:], flush=True)
    return out


def upsert_env(c: paramiko.SSHClient, kv: dict[str, str]) -> None:
    # 用 python 合并 .env，避免重复键
    payload = repr(kv)
    run(
        c,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        f"kv = {payload}\n"
        "from pathlib import Path\n"
        "p = Path('.env')\n"
        "lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else []\n"
        "keys = set(kv)\n"
        "out = []\n"
        "seen = set()\n"
        "for line in lines:\n"
        "    if not line.strip() or line.lstrip().startswith('#') or '=' not in line:\n"
        "        out.append(line); continue\n"
        "    k = line.split('=',1)[0].strip()\n"
        "    if k in keys:\n"
        "        out.append(f'{k}={kv[k]}'); seen.add(k)\n"
        "    else:\n"
        "        out.append(line)\n"
        "for k,v in kv.items():\n"
        "    if k not in seen:\n"
        "        out.append(f'{k}={v}')\n"
        "p.write_text('\\n'.join(out)+'\\n', encoding='utf-8')\n"
        "print('env_updated', sorted(kv))\n"
        "PY",
    )


def main() -> None:
    # 确保证书路径修复文件在两侧
    for role, units in (
        (
            "buyer",
            "agentlink-buyer-a agentlink-buyer-b agentlink-logistics "
            "agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics",
        ),
        (
            "supplier",
            "agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c",
        ),
    ):
        c = connect(role)
        with SCPClient(c.get_transport()) as scp:
            remote = "/opt/agentlink/commerce/_legacy/group_mq.py"
            run(c, "mkdir -p /opt/agentlink/commerce/_legacy")
            scp.put(str(ROOT / "commerce/_legacy/group_mq.py"), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/commerce/_legacy/group_mq.py 2>/dev/null || true")
        upsert_env(c, {**AICS, **EXTRA})
        run(c, f"systemctl restart {units}; sleep 3; systemctl is-active {units.split()[0]}")
        if role == "buyer":
            run(
                c,
                "cd /opt/agentlink && set -a && . ./.env && set +a && /opt/agentlink/.venv/bin/python - <<'PY'\n"
                "import asyncio, os\n"
                "from commerce._legacy import group_mq as g\n"
                "print('BUYER_A_AIC', os.getenv('BUYER_A_AIC'))\n"
                "print('paths', g._cert_paths('buyer-a'))\n"
                "print('partner_b', g.partner_aic('supplier-b'))\n"
                "print('partner_l', g.partner_aic('logistics'))\n"
                "async def main():\n"
                "  try:\n"
                "    rec = await asyncio.wait_for(\n"
                "      g.open_group(\n"
                "        leader_aic=os.environ['BUYER_A_AIC'],\n"
                "        leader_agent_id='buyer-a',\n"
                "        member_agent_ids=['supplier-b','supplier-c','logistics'],\n"
                "        invite=True,\n"
                "      ),\n"
                "      timeout=60,\n"
                "    )\n"
                "    sid = getattr(rec,'session_id',None) or getattr(rec,'group_id',None) or rec\n"
                "    print('OPEN_OK', sid)\n"
                "    print('invite_errors', getattr(rec,'invite_errors',None))\n"
                "    members = getattr(rec,'members',None) or getattr(rec,'member_rows',None)\n"
                "    print('members', members)\n"
                "  except Exception as e:\n"
                "    print('OPEN_FAIL', type(e).__name__, str(e)[:400])\n"
                "asyncio.run(main())\n"
                "PY",
            )
        c.close()
    print("SETUP_GROUP_AICS_DONE", flush=True)


if __name__ == "__main__":
    main()
