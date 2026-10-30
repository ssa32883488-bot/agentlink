"""Remote smoke after buyer V1 deploy."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

CHECK = r"""
set -e
echo '== services =='
systemctl is-active agentlink-buyer-a agentlink-ui-buyer
echo '== python =='
PY=
for p in /opt/agentlink/.venv/bin/python /opt/agentlink/venv/bin/python /usr/bin/python3; do
  if [ -x "$p" ]; then PY=$p; break; fi
done
echo "using $PY"
echo '== import =='
cd /opt/agentlink
$PY - <<'PY'
from commerce.buyer_tools.service import get_buyer_tools
from commerce.chat_buyer_wit import _build_capabilities, _extract_ui_widgets
caps = _build_capabilities(None)
print('caps', len(caps))
names = []
for c in caps:
    n = getattr(c, 'id', None) or getattr(c, '__name__', None) or type(c).__name__
    names.append(str(n))
need = ['discover.suppliers', 'rfq.send_batch', 'partner.dialog', 'memory.inject', 'calc.compare_table']
print('need_ok', all(any(x in n for n in names for x in [k]) or k in names for k in need))
print('names_has_discover', any('discover' in n for n in names))
print('names', names)
w = _extract_ui_widgets([{
  'result': {
    'case_id': 'c',
    'candidates': [{'candidate_id': 'x'}],
    'ui_hint': {'form': 'shortlist_confirm'},
  }
}])
print('widget', w[0]['kind'] if w else None)
print('mem', get_buyer_tools().memory.inject('smoke-mem', [{'key': 't', 'value': 1}])['ok'])
PY
echo '== grep ui =='
grep -n 'shortlist-form\|renderUiWidgets\|sendChatText' /opt/agentlink/ui/static/app.js | head
echo '== health =='
curl -sk -o /dev/null -w 'health=%{http_code}\n' https://127.0.0.1:8010/health
curl -sk -o /dev/null -w 'ui=%{http_code}\n' https://127.0.0.1:8090/
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
    _, stdout, stderr = c.exec_command(CHECK, timeout=90, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR:", err)
    c.close()


if __name__ == "__main__":
    main()
