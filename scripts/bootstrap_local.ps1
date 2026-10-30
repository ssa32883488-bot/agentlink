#Requires -Version 5.1
<#
.SYNOPSIS
  AgentLink 一键本地引导：venv + 依赖 + .env + 种子数据
.NOTES
  需已安装：Python 3.12+（或 uv）、可访问外网安装 pip 包
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root

function Have-Cmd([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host "==> AgentLink bootstrap @ $Root" -ForegroundColor Cyan

# --- Python / uv ---
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "==> Creating .venv (Python 3.12) ..."
    if (Have-Cmd "uv") {
        uv venv --python 3.12
    } elseif (Have-Cmd "py") {
        py -3.12 -m venv .venv
    } elseif (Have-Cmd "python") {
        python -m venv .venv
    } else {
        throw "未找到 Python / uv。请安装 Python 3.12+ 或 uv 后重试。"
    }
}

$Pip = Join-Path $Root ".venv\Scripts\pip.exe"
$Py = Join-Path $Root ".venv\Scripts\python.exe"

# --- vendor check ---
$Acps = Join-Path $Root "vendor\acps-sdk"
$Wit = Join-Path $Root "vendor\wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl"
if (-not (Test-Path $Acps)) {
    throw "缺少 vendor/acps-sdk。请使用正式发布包，或从 ACPs-community 拷贝 acps-sdk 到 vendor/。"
}
if (-not (Test-Path $Wit)) {
    throw "缺少 vendor/wit_framework-*.whl。请使用正式发布包。"
}

Write-Host "==> Installing dependencies ..."
& $Py -m pip install -U pip wheel setuptools
& $Pip install -e ".\vendor\acps-sdk"
& $Pip install $Wit
& $Pip install -r requirements-smoke.txt
& $Pip install "openai>=2.32.0,<3.0.0" "langgraph>=0.2.0" "langchain-core>=0.3.0" "kafka-python>=2.0.2"

# --- .env ---
$EnvFile = Join-Path $Root ".env"
$EnvExample = Join-Path $Root ".env.example"
if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "==> 已生成 .env（请编辑填入 LLM_API_KEY）" -ForegroundColor Yellow
} else {
    Write-Host "==> 已存在 .env，跳过复制"
}

# --- seed ---
Write-Host "==> Seeding demo catalogs ..."
& $Py -m commerce.seed

Write-Host ""
Write-Host "引导完成。" -ForegroundColor Green
Write-Host "1) 编辑 .env，填入 LLM_API_KEY（DeepSeek 等 OpenAI 兼容 Key）"
Write-Host "2) 启动六智能体:  .\scripts\start_all_local.ps1"
Write-Host "3) 启动本地 UI:  .\scripts\start_ui_local.ps1"
Write-Host "4) 打开 http://127.0.0.1:8090  （采购商A）"
Write-Host "可选冒烟:        .\.venv\Scripts\python.exe scripts\smoke_all_local.py"
