# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)

    def run(cmd: str) -> str:
        print("$", cmd[:160], flush=True)
        _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
        out = o.read().decode("utf-8", errors="replace")
        print(out[-3500:], flush=True)
        return out

    run(
        "systemctl cat agentlink-ui-supplier-a 2>/dev/null | head -40; "
        "echo '---'; "
        "ps aux | grep -E 'ui.app|8091|8093|8094' | grep -v grep | head -20"
    )
    run(
        "for p in 8091 8093 8094; do "
        "echo PORT $p; "
        "curl -sk -o /tmp/b -w 'https=%{http_code}\\n' --connect-timeout 3 https://127.0.0.1:$p/api/domain; "
        "curl -s -o /tmp/b -w 'http=%{http_code}\\n' --connect-timeout 3 http://127.0.0.1:$p/api/domain; "
        "head -c 100 /tmp/b; echo; "
        "done"
    )
    run(
        "ss -lntp | grep -E '8091|8093|8094|443|80'; "
        "ls /etc/nginx/conf.d 2>/dev/null; "
        "grep -R '8091\\|moknobita\\|supplier' /etc/nginx 2>/dev/null | head -40"
    )
    run("journalctl -u agentlink-ui-supplier-a -n 40 --no-pager")
    # restart UIs
    run(
        "systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; sleep 3; "
        "systemctl is-active agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c"
    )
    run(
        "for p in 8091 8093 8094; do "
        "echo PORT $p; "
        "curl -sk -o /tmp/b -w 'https=%{http_code} ' --connect-timeout 3 https://127.0.0.1:$p/api/domain; "
        "curl -s -o /tmp/b2 -w 'http=%{http_code}\\n' --connect-timeout 3 http://127.0.0.1:$p/api/domain; "
        "head -c 120 /tmp/b; echo; "
        "done"
    )
    c.close()


if __name__ == "__main__":
    main()
