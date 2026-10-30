# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    # put latest mailbox
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = b.open_sftp()
    sftp.put(str(ROOT / "commerce/mailbox.py"), "/opt/agentlink/commerce/mailbox.py")
    sftp.close()
    _, o, _ = b.exec_command(
        "systemctl restart agentlink-buyer-a; sleep 6; "
        "ss -lntp | grep -E ':8010|:8012|:8015' || true; "
        "curl -sk -o /tmp/m.json -w '%{http_code}' https://127.0.0.1:8010/api/erp/mailbox; echo; "
        "head -c 200 /tmp/m.json; echo; "
        "/opt/agentlink/.venv/bin/python -c \""
        "import json,urllib.request,ssl; ctx=ssl._create_unverified_context();\n"
        "def call(path,data=None):\n"
        "  req=urllib.request.Request('https://127.0.0.1:8010'+path, method='GET' if data is None else 'POST');\n"
        "  \n"
        "  if data is not None:\n"
        "    req.data=json.dumps(data).encode(); req.add_header('Content-Type','application/json')\n"
        "  with urllib.request.urlopen(req,context=ctx,timeout=45) as r: return json.loads(r.read().decode())\n"
        "print('email', call('/api/erp/mailbox').get('email'))\n"
        "t=call('/api/erp/tickets',{'title':'smoke2','kind':'procurement','peer_agent_id':'supplier-a','state':{'a':1}})\n"
        "print('ticket',t['id'],t['status'])\n"
        "print('suspend', call(f\\\"/api/erp/tickets/{t['id']}/suspend\\\", {'reason':'x','state':{'a':2}})['status'])\n"
        "print('resume', call(f\\\"/api/erp/tickets/{t['id']}/resume\\\", {})['status'])\n"
        "d=call(f\\\"/api/erp/tickets/{t['id']}/send-final-docs\\\", {'to_agent':'supplier-a','order_doc':{'order_no':'EO2','summary':'o'},'invoice_doc':{'invoice_no':'EI2','summary':'i'}})\n"
        "print('deliv', (d.get('order_mail') or {}).get('delivery'))\n"
        "tf=call(f\\\"/api/erp/tickets/{t['id']}\\\")\n"
        "print('done', tf.get('completion'), tf.get('status'))\n"
        "\"",
        timeout=180,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + b"\n")
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(
        "39.105.20.113",
        username="root",
        password=os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = s.open_sftp()
    sftp.put(str(ROOT / "commerce/mailbox.py"), "/opt/agentlink/commerce/mailbox.py")
    sftp.close()
    _, o, _ = s.exec_command(
        "systemctl restart agentlink-supplier-a; sleep 5; "
        "curl -sk https://127.0.0.1:8011/api/erp/mailbox | head -c 400; echo; "
        "curl -sk 'https://127.0.0.1:8011/api/erp/tickets' | head -c 500; echo",
        timeout=90,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + b"\n")
    s.close()


if __name__ == "__main__":
    main()
