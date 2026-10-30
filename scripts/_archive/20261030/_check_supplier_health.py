import os

import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(
    "39.105.20.113",
    username="root",
    password=os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"),
    timeout=30,
    allow_agent=False,
    look_for_keys=False,
)
cmd = r"""
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
curl -sk -o /dev/null -w 'a=%{http_code} ' https://127.0.0.1:8011/health
curl -sk -o /dev/null -w 'b=%{http_code} ' https://127.0.0.1:8013/health
curl -sk -o /dev/null -w 'c=%{http_code}\n' https://127.0.0.1:8014/health
grep -E '^(LOGISTICS_|ACPS_DISCOVERY)' /opt/agentlink/.env || true
journalctl -u agentlink-supplier-a -n 30 --no-pager | tail -n 30
"""
_, o, _ = c.exec_command(cmd, timeout=40, get_pty=True)
print(o.read().decode("utf-8", errors="replace"))
c.close()
