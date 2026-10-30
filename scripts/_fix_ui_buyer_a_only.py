# -*- coding: utf-8 -*-
"""8090 切到单智能体 buyer-a 配置，去掉顶栏三切换按钮。"""
from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
HOST = "81.70.46.119"


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )

    def run(cmd: str, timeout: int = 60) -> str:
        _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
        out = (o.read() + e.read()).decode("utf-8", "replace")
        print(out[-2500:], flush=True)
        return out

    print("=== discover ===", flush=True)
    run("systemctl list-units --type=service --all | grep -i agentlink | head -50")
    run("ls /etc/systemd/system/ | grep -iE 'agentlink|ui|8090' || true")
    run("ps aux | grep -E 'ui.app|uvicorn.*8090|AGENTLINK_UI' | grep -v grep || true")
    run("grep -R 'AGENTLINK_UI_CONFIG\\|config_buyer\\|ui.app\\|8090' /etc/systemd/system/ 2>/dev/null | head -60 || true")
    run("ls /etc/agentlink/ 2>/dev/null || true")

    # Prefer editing unit Environment=AGENTLINK_UI_CONFIG
    # Fallback: rewrite default config on disk to buyer-a content
    print("=== patch ===", flush=True)
    run(
        r"""
set -e
CFG_SRC=/opt/agentlink/ui/config_buyer_a.yaml
CFG_DST=/opt/agentlink/ui/config_buyer_domain.yaml
if [ -f "$CFG_SRC" ]; then
  # keep backup of aggregate config
  cp -a "$CFG_DST" /opt/agentlink/ui/config_buyer_domain.yaml.bak.$(date +%Y%m%d%H%M%S) 2>/dev/null || true
  # make default aggregate file become single-agent (covers units that still point at buyer_domain)
  cp -a "$CFG_SRC" "$CFG_DST"
  # also ensure buyer_a file title/port ok
  sed -i 's/domain_title:.*/domain_title: 采购商A · 采联控制台/' "$CFG_DST"
  sed -i 's/domain_id:.*/domain_id: buyer-a/' "$CFG_DST"
  echo '--- new domain config ---'
  cat "$CFG_DST"
fi

# patch any systemd units that hardcode buyer_domain
for f in /etc/systemd/system/*.service; do
  if grep -q 'AGENTLINK_UI_CONFIG\|config_buyer_domain\|ui.app\|8090' "$f" 2>/dev/null; then
    echo "UNIT $f"
    grep -n 'AGENTLINK_UI_CONFIG\|config_buyer\|UI_PORT\|8090\|ExecStart' "$f" || true
    if grep -q 'config_buyer_domain.yaml' "$f"; then
      sed -i 's#config_buyer_domain.yaml#config_buyer_a.yaml#g' "$f"
      echo PATCHED_UNIT "$f"
    fi
  fi
done
systemctl daemon-reload || true

# restart likely UI units
for u in agentlink-ui-buyer-a agentlink-ui-buyer agentlink-buyer-ui agentlink-ui agentlink-ui-8090; do
  if systemctl list-unit-files | grep -q "^${u}"; then
    systemctl restart "$u" || true
    echo RESTARTED "$u"
  fi
done

# also restart any unit listening 8090
UNIT=$(systemctl list-units --type=service --all --no-legend | awk '{print $1}' | while read u; do
  systemctl show -p FragmentPath "$u" 2>/dev/null | grep -q . && \
  grep -l '8090\|config_buyer' $(systemctl show -p FragmentPath --value "$u") 2>/dev/null && echo "$u"
done | head -5)
echo FOUND_UNITS "$UNIT"
for u in $UNIT; do systemctl restart "$u" || true; echo RESTARTED2 "$u"; done

# brute: kill uvicorn on 8090 and start buyer-a if needed
PIDS=$(ss -lptn 'sport = :8090' 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u)
echo PIDS8090 "$PIDS"
"""
    )

    time.sleep(2)
    print("=== verify ===", flush=True)
    run(
        "python3 - <<'PY'\n"
        "import json,urllib.request,ssl\n"
        "ctx=ssl._create_unverified_context()\n"
        "u='https://127.0.0.1:8090/api/domain'\n"
        "try:\n"
        "  d=json.loads(urllib.request.urlopen(u,context=ctx,timeout=10).read().decode())\n"
        "  print('domain', d.get('domain_id'), d.get('domain_title'))\n"
        "  print('agents', [a.get('id') for a in d.get('agents') or []])\n"
        "  print('config', d.get('config_path'))\n"
        "except Exception as e:\n"
        "  print('ERR', e)\n"
        "PY"
    )
    c.close()


if __name__ == "__main__":
    main()
