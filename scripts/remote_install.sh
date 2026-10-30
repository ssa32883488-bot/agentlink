#!/usr/bin/env bash
# 在服务器上：解压 /opt/agentlink_bundle → 装 Python3.12 + 依赖 → 写 systemd
set -euo pipefail
ROLE="${1:?usage: remote_install.sh buyer|supplier}"
BUNDLE="${2:-/opt/agentlink_bundle}"
APP="/opt/agentlink"
PY312=""

export DEBIAN_FRONTEND=noninteractive

install_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  export PATH="$HOME/.local/bin:/root/.local/bin:$PATH"
}

echo "== role=$ROLE bundle=$BUNDLE =="
test -d "$BUNDLE/agentlink"
test -d "$BUNDLE/vendor"

install_uv
uv python install 3.12
PYBIN="$(uv python find 3.12)"
echo "python=$PYBIN"

if [ -e "$APP" ]; then
  chmod -R u+w "$APP" 2>/dev/null || true
  rm -rf "$APP" || { find "$APP" -mindepth 1 -delete 2>/dev/null || true; rm -rf "$APP"; }
fi
mkdir -p /opt
cp -a "$BUNDLE/agentlink" "$APP"
cd "$APP"

uv venv --python 3.12 .venv
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -e "$BUNDLE/vendor/acps-sdk" -r requirements-smoke.txt
if ls "$BUNDLE/vendor"/wit_framework-*.whl >/dev/null 2>&1; then
  uv pip install "$BUNDLE/vendor"/wit_framework-*.whl || true
fi
uv pip install openai pyyaml httpx uvicorn fastapi pydantic pydantic-settings

# 最小 .env（无密钥也可起 RPC；LLM 可选）
if [ ! -f .env ]; then
  cat > .env <<'EOF'
BUYER_CHAT_ENGINE=rules
AIP_IDENTITY_BINDING=0
EOF
fi

mkdir -p /var/log/agentlink /etc/agentlink /etc/agentlink/tls

# 公网 IP（用于自签证书 SAN）；平台 ACS 要求 https:// 完整 URL
PUBLIC_IP=""
if [ "$ROLE" = "buyer" ]; then
  PUBLIC_IP="${AGENTLINK_PUBLIC_IP:-81.70.46.119}"
else
  PUBLIC_IP="${AGENTLINK_PUBLIC_IP:-39.105.20.113}"
fi

ensure_tls_cert() {
  local ip="$1"
  local crt="/etc/agentlink/tls/server.crt"
  local key="/etc/agentlink/tls/server.key"
  local cfg="/etc/agentlink/tls/openssl.cnf"
  if [ -f "$crt" ] && [ -f "$key" ]; then
    echo "TLS cert exists: $crt"
    return 0
  fi
  echo "Generating self-signed TLS cert for IP $ip ..."
  cat > "$cfg" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
C = CN
O = AgentLink
CN = ${ip}

[v3_req]
subjectAltName = @alt
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt]
IP.1 = ${ip}
EOF
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$key" -out "$crt" -days 825 \
    -config "$cfg" -extensions v3_req
  chmod 600 "$key"
  chmod 644 "$crt"
  echo "TLS ready: $crt"
}

ensure_tls_cert "$PUBLIC_IP"
TLS_CRT=/etc/agentlink/tls/server.crt
TLS_KEY=/etc/agentlink/tls/server.key

write_unit() {
  local name="$1" module="$2" port="$3"
  cat > "/etc/systemd/system/agentlink-${name}.service" <<EOF
[Unit]
Description=AgentLink ${name} (HTTPS)
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP}
Environment=AIP_IDENTITY_BINDING=0
Environment=AIP_SSL_INSECURE=1
Environment=AGENTLINK_RUNTIME=v2
Environment=V2_LOCAL_PARTNERS=0
Environment=PORT=${port}
Environment=HOST=0.0.0.0
EnvironmentFile=-${APP}/.env
ExecStart=${APP}/.venv/bin/python -m uvicorn ${module} --host 0.0.0.0 --port ${port} --ssl-certfile ${TLS_CRT} --ssl-keyfile ${TLS_KEY}
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/${name}.log
StandardError=append:/var/log/agentlink/${name}.log

[Install]
WantedBy=multi-user.target
EOF
}

upsert_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$APP/.env" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$APP/.env"
  else
    echo "${key}=${val}" >> "$APP/.env"
  fi
}

if [ "$ROLE" = "buyer" ]; then
  # 计划端口 8010/8012；若 education-agent 占 8010 则停掉以免冲突
  if command -v docker >/dev/null 2>&1; then
    if docker ps --format '{{.Names}} {{.Ports}}' | grep -q '0.0.0.0:8010'; then
      echo "WARN: freeing :8010 (stopping container bound to 8010)"
      docker ps --format '{{.ID}} {{.Ports}}' | awk '/0.0.0.0:8010/{print $1}' | xargs -r docker stop || true
    fi
  fi
  write_unit buyer-a agents.buyer_a.main:app 8010
  write_unit buyer-b agents.buyer_b.main:app 8012
  write_unit logistics agents.logistics.main:app 8015
  # 同机物流走本机 HTTPS；跨机供应商用公网 HTTPS（自签需 AIP_SSL_INSECURE=1）
  upsert_env LOGISTICS_RPC_URL "https://127.0.0.1:8015/rpc"
  # 腾讯云侧解析/连通 moknobita 域名常失败，跨云 AIP 默认走阿里云公网 IP
  upsert_env SUPPLIER_A_RPC_URL "https://39.105.20.113:8011/rpc"
  upsert_env SUPPLIER_B_RPC_URL "https://39.105.20.113:8013/rpc"
  upsert_env SUPPLIER_C_RPC_URL "https://39.105.20.113:8014/rpc"
  # Let's Encrypt 公网证书可校验证书；本机 127.0.0.1 自签/本机名仍可能需 insecure
  upsert_env AIP_SSL_INSECURE "1"
  upsert_env AGENTLINK_RUNTIME "v2"
  upsert_env V2_LOCAL_PARTNERS "0"
  # 梧桐 Discovery（ADP）——采购发现必须走平台，禁止只靠本地黄页
  upsert_env ACPS_DISCOVERY_URL "https://wt.ioa.pub/discovery"
  upsert_env V2_DISCOVERY_MODE "auto"
  systemctl daemon-reload
  systemctl enable --now agentlink-buyer-a.service agentlink-buyer-b.service agentlink-logistics.service
  systemctl restart agentlink-buyer-a.service agentlink-buyer-b.service agentlink-logistics.service
elif [ "$ROLE" = "supplier" ]; then
  write_unit supplier-a agents.supplier_a.main:app 8011
  write_unit supplier-b agents.supplier_b.main:app 8013
  write_unit supplier-c agents.supplier_c.main:app 8014
  # 物流已迁至腾讯云；停掉本机旧 logistics（若有）
  systemctl disable --now agentlink-logistics.service 2>/dev/null || true
  rm -f /etc/systemd/system/agentlink-logistics.service
  # 供应确认 Gate 后回写采购云工单
  upsert_env BUYER_A_RPC_URL "https://81.70.46.119:8010/rpc"
  upsert_env BUYER_B_RPC_URL "https://81.70.46.119:8012/rpc"
  upsert_env LOGISTICS_RPC_URL "https://81.70.46.119:8015/rpc"
  upsert_env AIP_SSL_INSECURE "1"
  upsert_env AGENTLINK_RUNTIME "v2"
  upsert_env V2_LOCAL_PARTNERS "0"
  systemctl daemon-reload
  systemctl enable --now agentlink-supplier-a.service agentlink-supplier-b.service agentlink-supplier-c.service
  systemctl restart agentlink-supplier-a.service agentlink-supplier-b.service agentlink-supplier-c.service
else
  echo "unknown role" >&2
  exit 1
fi

# 尽量放行本机防火墙（云安全组仍需控制台放行）
if command -v firewall-cmd >/dev/null 2>&1; then
  if [ "$ROLE" = "buyer" ]; then
    firewall-cmd --permanent --add-port=8010/tcp || true
    firewall-cmd --permanent --add-port=8012/tcp || true
    firewall-cmd --permanent --add-port=8015/tcp || true
  else
    firewall-cmd --permanent --add-port=8011/tcp || true
    firewall-cmd --permanent --add-port=8013/tcp || true
    firewall-cmd --permanent --add-port=8014/tcp || true
  fi
  firewall-cmd --reload || true
fi

sleep 2
echo "== listening =="
ss -lntp | grep -E '8010|8012|8015|8011|8013|8014' || true
echo "OK"
