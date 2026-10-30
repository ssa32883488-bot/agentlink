# 三个独立链接：
#   座椅商城      :8080
#   采购商管理后台 :8090
#   供应商管理后台 :8091（无对外门户，仅管理）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"

$env:AIP_IDENTITY_BINDING = "0"
$env:BUYER_A_API = "http://127.0.0.1:8010"

Write-Host "启动座椅商城 :8080 ..."
$env:MALL_PORT = "8080"
Start-Process -FilePath $Py -ArgumentList "-m","ui.mall_app" -WorkingDirectory $Root -WindowStyle Minimized

Start-Sleep -Milliseconds 500
Write-Host "启动采购商管理后台 :8090 ..."
$env:AGENTLINK_UI_CONFIG = Join-Path $Root "ui\config_buyer_domain.yaml"
$env:UI_PORT = "8090"
Start-Process -FilePath $Py -ArgumentList "-m","ui.app" -WorkingDirectory $Root -WindowStyle Minimized

Start-Sleep -Milliseconds 500
Write-Host "启动供应商管理后台 :8091 ..."
$env:AGENTLINK_UI_CONFIG = Join-Path $Root "ui\config_supplier_domain.yaml"
$env:UI_PORT = "8091"
Start-Process -FilePath $Py -ArgumentList "-m","ui.app" -WorkingDirectory $Root -WindowStyle Minimized

Write-Host ""
Write-Host "座椅商城（C端）:     http://127.0.0.1:8080"
Write-Host "采购商管理后台:     http://127.0.0.1:8090"
Write-Host "供应商管理后台:     http://127.0.0.1:8091"
Write-Host "请先启动 Agent: .\scripts\start_all_local.ps1"
