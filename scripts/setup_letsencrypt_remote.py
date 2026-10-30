# -*- coding: utf-8 -*-
"""在腾讯云/阿里云申请 Let's Encrypt 证书并挂到 AgentLink HTTPS 端口。

域名约定：
  ashui.online     -> 81.70.46.119  (buyer/logistics)
  moknobita.xyz    -> 39.105.20.113 (suppliers)

HTTP-01 需短暂停用占用 :80 的服务（buyer: nginx；supplier: docker-frontend）。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
EMAIL = os.environ.get("LE_EMAIL", "3572962849@qq.com")

BUYER = {
    "host": "81.70.46.119",
    "auth": "key",
    "domain": "ashui.online",
    "www": "www.ashui.online",
    "role": "buyer",
    "services": "agentlink-buyer-a.service agentlink-buyer-b.service agentlink-logistics.service",
    "stop80": "systemctl stop nginx || true",
    "start80": "systemctl start nginx || true",
}
SUPPLIER = {
    "host": "39.105.20.113",
    "auth": "password",
    "password": os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"),
    "domain": "moknobita.xyz",
    "www": "www.moknobita.xyz",
    "role": "supplier",
    "services": "agentlink-supplier-a.service agentlink-supplier-b.service agentlink-supplier-c.service",
    "stop80": "docker stop docker-frontend-1 || true",
    "start80": "docker start docker-frontend-1 || true",
}


def connect(spec: dict) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if spec["auth"] == "key":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(spec["host"], username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            spec["host"],
            username="root",
            password=spec["password"],
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 600, check: bool = True) -> str:
    print(f"$ {cmd}")
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    text = (out + err)[-6000:]
    print(text)
    if check and code != 0:
        raise SystemExit(f"remote exit {code}: {cmd}")
    return out


REMOTE_SH = r"""#!/usr/bin/env bash
set -euo pipefail
DOMAIN="$1"
WWW="$2"
EMAIL="$3"
SERVICES="$4"
STOP80="$5"
START80="$6"

export PATH="$HOME/.acme.sh:/root/.acme.sh:$HOME/.local/bin:/usr/local/bin:$PATH"
mkdir -p /etc/agentlink/tls /var/log/agentlink

# 国内机访问 get.acme.sh 常超时：优先 gitee 克隆安装
if [ ! -f /root/.acme.sh/acme.sh ]; then
  if [ ! -f /root/acme.sh/acme.sh ]; then
    dnf install -y git >/dev/null 2>&1 || yum install -y git >/dev/null 2>&1 || true
    git clone --depth 1 https://gitee.com/neilpang/acme.sh.git /root/acme.sh
  fi
  cd /root/acme.sh && ./acme.sh --install -m "$EMAIL"
fi
# shellcheck disable=SC1091
source /root/.acme.sh/acme.sh.env 2>/dev/null || true
export PATH="/root/.acme.sh:$PATH"

# 使用 Let's Encrypt 正式 CA
/root/.acme.sh/acme.sh --set-default-ca --server letsencrypt || true

echo "== freeing :80 for HTTP-01 =="
bash -c "$STOP80"
sleep 2
ss -lntp | grep ':80 ' || echo "port 80 free"

echo "== issuing cert for $DOMAIN =="
# 已存在则 force 续签/重签
if [ -d "/root/.acme.sh/${DOMAIN}_ecc" ] || [ -d "/root/.acme.sh/${DOMAIN}" ]; then
  /root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --force --server letsencrypt || \
  /root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --force --server letsencrypt -k 2048
else
  /root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --server letsencrypt || \
  /root/.acme.sh/acme.sh --issue -d "$DOMAIN" -d "$WWW" --standalone --server letsencrypt -k 2048
fi

echo "== restore :80 service =="
bash -c "$START80" || true

RELOAD="systemctl restart $SERVICES"
/root/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
  --fullchain-file /etc/agentlink/tls/fullchain.pem \
  --key-file /etc/agentlink/tls/privkey.pem \
  --reloadcmd "$RELOAD"

chmod 600 /etc/agentlink/tls/privkey.pem
chmod 644 /etc/agentlink/tls/fullchain.pem
# 兼容旧单元名
ln -sfn /etc/agentlink/tls/fullchain.pem /etc/agentlink/tls/server.crt
ln -sfn /etc/agentlink/tls/privkey.pem /etc/agentlink/tls/server.key

# 把 systemd 单元的证书路径切到 LE 文件（若仍指向旧路径则替换）
for u in $SERVICES; do
  f="/etc/systemd/system/${u}"
  if [ -f "$f" ]; then
    sed -i 's|--ssl-certfile [^ ]*|--ssl-certfile /etc/agentlink/tls/fullchain.pem|' "$f"
    sed -i 's|--ssl-keyfile [^ ]*|--ssl-keyfile /etc/agentlink/tls/privkey.pem|' "$f"
  fi
done
systemctl daemon-reload
systemctl restart $SERVICES
sleep 2
ss -lntp | grep -E '8010|8011|8012|8013|8014|8015' || true
openssl x509 -in /etc/agentlink/tls/fullchain.pem -noout -subject -issuer -dates | head -20
echo "LE_OK $DOMAIN"
"""


def setup(spec: dict) -> None:
    print(f"\n==== LE {spec['role']} {spec['host']} {spec['domain']} ====")
    c = connect(spec)
    run(c, "mkdir -p /tmp")
    with SCPClient(c.get_transport()) as scp:
        local = ROOT / "scripts" / "_le_remote.sh"
        local.write_text(REMOTE_SH.replace("\r\n", "\n"), encoding="utf-8")
        scp.put(str(local), "/tmp/_le_remote.sh")
    run(c, "sed -i 's/\\r$//' /tmp/_le_remote.sh && chmod +x /tmp/_le_remote.sh")
    # quote args carefully
    cmd = (
        f"bash /tmp/_le_remote.sh "
        f"{spec['domain']} {spec['www']} {EMAIL} "
        f"'{spec['services']}' "
        f"'{spec['stop80']}' "
        f"'{spec['start80']}'"
    )
    run(c, cmd, timeout=900)
    c.close()
    print(f"done {spec['host']}")


def main() -> None:
    targets = sys.argv[1:] or ["buyer", "supplier"]
    if "buyer" in targets:
        setup(BUYER)
    if "supplier" in targets:
        setup(SUPPLIER)


if __name__ == "__main__":
    main()
