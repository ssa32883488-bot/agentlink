# 部署供应/物流侧到阿里云 39.105.20.113
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py (Join-Path $Root "scripts\pack_for_remote.py")
& $Py (Join-Path $Root "scripts\deploy_remote.py") supplier
Write-Host "放行阿里云安全组 TCP 8011,8013,8014 后探测对应 /health（物流在腾讯云 :8015）"
