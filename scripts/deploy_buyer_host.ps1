# 部署采购侧到腾讯云 81.70.46.119
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py (Join-Path $Root "scripts\pack_for_remote.py")
& $Py (Join-Path $Root "scripts\deploy_remote.py") buyer
Write-Host "放行腾讯云安全组 TCP 8010,8012,8015 后探测 buyer/logistics /health"
