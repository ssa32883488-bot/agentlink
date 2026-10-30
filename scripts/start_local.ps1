# 本地启动采购 A + 供应商 A（两个后台窗口）
# 用法：在 agentlink 目录执行 .\scripts\start_local.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "未找到 .venv，正在创建..."
    uv venv --python 3.12
    uv pip install -e "..\..\ACPs-community\acps-sdk" -r requirements-smoke.txt
}

$env:AIP_IDENTITY_BINDING = "0"
$env:BUYER_A_AIC = "buyer-a-local-aic"
$env:SUPPLIER_A_AIC = "supplier-a-local-aic"

Write-Host "启动供应商 A :8011 ..."
Start-Process -FilePath $Py -ArgumentList "-m","uvicorn","agents.supplier_a.main:app","--host","127.0.0.1","--port","8011" -WorkingDirectory $Root -WindowStyle Minimized

Start-Sleep -Seconds 1
Write-Host "启动采购 A :8010 ..."
Start-Process -FilePath $Py -ArgumentList "-m","uvicorn","agents.buyer_a.main:app","--host","127.0.0.1","--port","8010" -WorkingDirectory $Root -WindowStyle Minimized

Write-Host ""
Write-Host "已启动。冒烟命令："
Write-Host "  .\.venv\Scripts\python.exe scripts\smoke_local.py"
Write-Host "健康检查："
Write-Host "  http://127.0.0.1:8010/health"
Write-Host "  http://127.0.0.1:8011/health"
