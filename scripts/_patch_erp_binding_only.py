# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem")

PATCH = r"""
set -e
for ag in supplier-a supplier-b supplier-c; do
  unit=/etc/systemd/system/agentlink-${ag}-erp.service
  sed -i 's/AIP_IDENTITY_BINDING=0/AIP_IDENTITY_BINDING=1/' "$unit" || true
  envf=/etc/agentlink/${ag}.env
  if [ -f "$envf" ]; then
    if grep -q '^AIP_IDENTITY_BINDING=' "$envf"; then sed -i 's/^AIP_IDENTITY_BINDING=.*/AIP_IDENTITY_BINDING=1/' "$envf"; else echo 'AIP_IDENTITY_BINDING=1' >> "$envf"; fi
    if grep -q '^ACPS_GROUP_IDENTITY_BINDING=' "$envf"; then sed -i 's/^ACPS_GROUP_IDENTITY_BINDING=.*/ACPS_GROUP_IDENTITY_BINDING=1/' "$envf"; else echo 'ACPS_GROUP_IDENTITY_BINDING=1' >> "$envf"; fi
  fi
  echo patched_$ag
done
systemctl daemon-reload
grep AIP_IDENTITY /etc/systemd/system/agentlink-supplier-a-erp.service || true
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(PATCH, timeout=30, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    for unit in (
        "agentlink-supplier-a-erp",
        "agentlink-supplier-b-erp",
        "agentlink-supplier-c-erp",
    ):
        _, o, e = c.exec_command(f"systemctl restart {unit}; sleep 2; systemctl is-active {unit}", timeout=45, get_pty=True)
        print(unit, (o.read() + e.read()).decode("utf-8", "replace").strip())
    c.close()

    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(PEM),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    cmd = r"""
set -e
f=/etc/agentlink/buyer-a.env
grep -q '^ACPS_GROUP_INVITE_TIMEOUT_SEC=' $f && sed -i 's/^ACPS_GROUP_INVITE_TIMEOUT_SEC=.*/ACPS_GROUP_INVITE_TIMEOUT_SEC=25/' $f || echo 'ACPS_GROUP_INVITE_TIMEOUT_SEC=25' >> $f
grep -q '^ACPS_GROUP_MIN_SUPPLIERS=' $f && sed -i 's/^ACPS_GROUP_MIN_SUPPLIERS=.*/ACPS_GROUP_MIN_SUPPLIERS=1/' $f || echo 'ACPS_GROUP_MIN_SUPPLIERS=1' >> $f
systemctl restart agentlink-buyer-a
sleep 4
systemctl is-active agentlink-buyer-a
grep ACPS_GROUP $f
"""
    _, o, e = b.exec_command(cmd, timeout=60, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    b.close()
    print("PATCH_DONE")


if __name__ == "__main__":
    main()
