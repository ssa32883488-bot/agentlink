#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
mkdir -p logs

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export AIP_IDENTITY_BINDING="${AIP_IDENTITY_BINDING:-0}"
export AGENTLINK_RUNTIME="${AGENTLINK_RUNTIME:-v2}"
export BUYER_A_API="http://127.0.0.1:8010"

start_ui() {
  local cfg="$1" port="$2" name="$3"
  echo "启动 $name :$port"
  export AGENTLINK_UI_CONFIG="$ROOT/$cfg"
  export UI_PORT="$port"
  nohup "$PY" -m ui.app >"logs/ui_${name}.out" 2>&1 &
  echo $! >"logs/ui_${name}.pid"
  sleep 0.3
}

echo "启动座椅商城 :8080 ..."
export MALL_PORT=8080
nohup "$PY" -m ui.mall_app >logs/ui_mall.out 2>&1 &
echo $! >logs/ui_mall.pid
sleep 0.4

start_ui ui/local/config_buyer_a.yaml 8090 buyer_a
start_ui ui/local/config_buyer_b.yaml 8092 buyer_b
start_ui ui/local/config_logistics.yaml 8095 logistics
start_ui ui/local/config_supplier_a.yaml 8091 supplier_a
start_ui ui/local/config_supplier_b.yaml 8093 supplier_b
start_ui ui/local/config_supplier_c.yaml 8094 supplier_c

echo ""
echo "采购商A: http://127.0.0.1:8090"
echo "请确认 Agent 已启动: ./scripts/start_all_local.sh"
