#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "请先运行 ./scripts/bootstrap_local.sh" >&2
  exit 1
fi

# load .env
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export AIP_IDENTITY_BINDING="${AIP_IDENTITY_BINDING:-0}"
export AGENTLINK_RUNTIME="${AGENTLINK_RUNTIME:-v2}"

start_one() {
  local name="$1" module="$2" port="$3"
  echo "启动 $name :$port"
  nohup "$PY" -m uvicorn "$module" --host 127.0.0.1 --port "$port" \
    >"logs/${name}.out" 2>&1 &
  echo $! >"logs/${name}.pid"
  sleep 0.3
}

mkdir -p logs
start_one supplier_a agents.supplier_a.main:app 8011
start_one supplier_b agents.supplier_b.main:app 8013
start_one supplier_c agents.supplier_c.main:app 8014
start_one logistics  agents.logistics.main:app  8015
start_one buyer_a    agents.buyer_a.main:app    8010
start_one buyer_b    agents.buyer_b.main:app    8012

echo ""
echo "全部已拉起。验证: .venv/bin/python scripts/smoke_all_local.py"
