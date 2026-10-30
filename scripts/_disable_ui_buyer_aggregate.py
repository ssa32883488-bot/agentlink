# -*- coding: utf-8 -*-
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

    def run(cmd: str) -> str:
        _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
        out = (o.read() + e.read()).decode("utf-8", "replace")
        print(out[-2000:], flush=True)
        return out

    # Stop aggregate UI; keep single-agent buyer-a on 8090
    run(
        "systemctl stop agentlink-ui-buyer; "
        "systemctl disable agentlink-ui-buyer; "
        "systemctl reset-failed agentlink-ui-buyer-a || true; "
        "systemctl restart agentlink-ui-buyer-a; "
        "sleep 2; "
        "systemctl is-active agentlink-ui-buyer-a; "
        "systemctl is-active agentlink-ui-buyer || true; "
        "ss -lptn 'sport = :8090' || true"
    )
    # Restore mall config to something harmless (mall_app may ignore agents)
    run(
        "grep -n AGENTLINK_UI_CONFIG /etc/systemd/system/agentlink-ui-mall.service; "
        "sed -i 's#config_buyer_a.yaml#config_buyer_domain.yaml#g' /etc/systemd/system/agentlink-ui-mall.service || true; "
        # domain yaml is already single-agent copy; fine for mall
        "systemctl daemon-reload; systemctl restart agentlink-ui-mall || true"
    )
    run(
        "python3 - <<'PY'\n"
        "import json,urllib.request,ssl\n"
        "ctx=ssl._create_unverified_context()\n"
        "for u in ['https://127.0.0.1:8090/api/domain','https://127.0.0.1:8092/api/domain','https://127.0.0.1:8095/api/domain']:\n"
        "  d=json.loads(urllib.request.urlopen(u,context=ctx,timeout=10).read().decode())\n"
        "  print(u, d.get('domain_id'), [a.get('id') for a in d.get('agents') or []])\n"
        "PY"
    )
    c.close()


if __name__ == "__main__":
    main()
