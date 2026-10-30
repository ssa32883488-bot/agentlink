#!/usr/bin/env bash
# AgentLink 一键本地引导：venv + 依赖 + .env + 种子数据
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> AgentLink bootstrap @ $ROOT"

if [[ ! -d .venv ]]; then
  echo "==> Creating .venv (Python 3.12) ..."
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12
  elif command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv .venv
  else
    python3 -m venv .venv
  fi
fi

PY="$ROOT/.venv/bin/python"
PIP="$ROOT/.venv/bin/pip"

if [[ ! -d vendor/acps-sdk ]]; then
  echo "缺少 vendor/acps-sdk" >&2
  exit 1
fi
if [[ ! -f vendor/wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl ]]; then
  echo "缺少 vendor/wit_framework-*.whl" >&2
  exit 1
fi

echo "==> Installing dependencies ..."
"$PY" -m pip install -U pip wheel setuptools
"$PIP" install -e ./vendor/acps-sdk
"$PIP" install ./vendor/wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl
"$PIP" install -r requirements-smoke.txt
"$PIP" install "openai>=2.32.0,<3.0.0" "langgraph>=0.2.0" "langchain-core>=0.3.0" "kafka-python>=2.0.2"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> 已生成 .env（请编辑填入 LLM_API_KEY）"
fi

echo "==> Seeding demo catalogs ..."
"$PY" -m commerce.seed

echo ""
echo "引导完成。"
echo "1) 编辑 .env，填入 LLM_API_KEY"
echo "2) 启动六智能体:  ./scripts/start_all_local.sh"
echo "3) 启动本地 UI:  ./scripts/start_ui_local.sh"
echo "4) 打开 http://127.0.0.1:8090"
