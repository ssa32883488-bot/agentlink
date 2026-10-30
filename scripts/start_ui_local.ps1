# 本地 HTTP 六控制台 + 商城（需先 start_all_local）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "请先运行 .\scripts\bootstrap_local.ps1" }

# 加载 .env（简单解析 KEY=VALUE）
$EnvPath = Join-Path $Root ".env"
if (Test-Path $EnvPath) {
    Get-Content $EnvPath | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $i = $_.IndexOf('=')
        if ($i -lt 1) { return }
        $k = $_.Substring(0, $i).Trim()
        $v = $_.Substring($i + 1).Trim()
        [Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
}

$env:AIP_IDENTITY_BINDING = if ($env:AIP_IDENTITY_BINDING) { $env:AIP_IDENTITY_BINDING } else { "0" }
$env:AGENTLINK_RUNTIME = if ($env:AGENTLINK_RUNTIME) { $env:AGENTLINK_RUNTIME } else { "v2" }
$env:BUYER_A_API = "http://127.0.0.1:8010"

function Start-Ui([string]$ConfigRel, [int]$Port, [string]$Title) {
    Write-Host "启动 $Title :$Port ..."
    $env:AGENTLINK_UI_CONFIG = Join-Path $Root $ConfigRel
    $env:UI_PORT = "$Port"
    Start-Process -FilePath $Py -ArgumentList "-m", "ui.app" -WorkingDirectory $Root -WindowStyle Minimized
    Start-Sleep -Milliseconds 350
}

Write-Host "启动座椅商城 :8080 ..."
$env:MALL_PORT = "8080"
Start-Process -FilePath $Py -ArgumentList "-m", "ui.mall_app" -WorkingDirectory $Root -WindowStyle Minimized
Start-Sleep -Milliseconds 400

Start-Ui "ui\local\config_buyer_a.yaml" 8090 "采购商A"
Start-Ui "ui\local\config_buyer_b.yaml" 8092 "采购商B"
Start-Ui "ui\local\config_logistics.yaml" 8095 "物流"
Start-Ui "ui\local\config_supplier_a.yaml" 8091 "供应商A"
Start-Ui "ui\local\config_supplier_b.yaml" 8093 "供应商B"
Start-Ui "ui\local\config_supplier_c.yaml" 8094 "供应商C"

Write-Host ""
Write-Host "座椅商城:     http://127.0.0.1:8080"
Write-Host "采购商A:      http://127.0.0.1:8090"
Write-Host "采购商B:      http://127.0.0.1:8092"
Write-Host "物流:         http://127.0.0.1:8095"
Write-Host "供应商A/B/C:  http://127.0.0.1:8091 / 8093 / 8094"
Write-Host "请确认六 Agent 已启动: .\scripts\start_all_local.ps1"
