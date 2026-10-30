# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

CMD = r"""
echo '=== keystores ==='
ls -la /root/.keystore /etc/agentlink/tls/*.jks /etc/agentlink/tls/*.p12 /opt/agentlink/**/*.jks 2>/dev/null
find /etc/agentlink /opt/agentlink/java-suppliers /root -maxdepth 3 -name '*.jks' -o -name '*.p12' -o -name '.keystore' 2>/dev/null | head -40
echo '=== root keystore aliases ==='
for store in /root/.keystore; do
  [ -f "$store" ] || continue
  keytool -list -keystore "$store" -storepass changeit 2>/dev/null || keytool -list -keystore "$store" -storepass tomcat 2>/dev/null || keytool -list -keystore "$store" -storepass password 2>/dev/null || echo FAIL_LIST
done
echo '=== application yml/props ==='
find /opt/agentlink/java-suppliers -type f \( -name '*.yml' -o -name '*.yaml' -o -name '*.properties' \) 2>/dev/null | head -40
for f in $(find /opt/agentlink/java-suppliers -type f \( -name 'application*.yml' -o -name 'application*.properties' \) 2>/dev/null); do
  echo "-- $f --"; grep -nE 'ssl|keystore|key-store|cert' "$f" | head -30
done
echo '=== jar internal application.yml ==='
cd /tmp
jar xf /opt/agentlink/java-suppliers/supplier-a.jar BOOT-INF/classes/application.yml BOOT-INF/classes/application.properties 2>/dev/null || true
ls -la BOOT-INF/classes/application* 2>/dev/null
grep -nE 'ssl|keystore|key-store|cert|8011' BOOT-INF/classes/application* 2>/dev/null | head -50
echo '=== live after wait ==='
sleep 3
ss -lntp | grep 8011 || true
echo | timeout 5 openssl s_client -connect 127.0.0.1:8011 2>/dev/null | openssl x509 -noout -subject || echo NO_CERT
"""


def main() -> None:
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = s.exec_command(CMD, timeout=90)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    s.close()


if __name__ == "__main__":
    main()
