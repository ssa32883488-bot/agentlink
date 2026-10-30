# 启动全部 6 个本地 Agent 进程（HTTP）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "未找到 .venv，先执行 bootstrap ..."
    & (Join-Path $Root "scripts\bootstrap_local.ps1")
}

# 加载 .env
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

$procs = @(
    @{ Name = "supplier_a"; Module = "agents.supplier_a.main:app"; Port = 8011 },
    @{ Name = "supplier_b"; Module = "agents.supplier_b.main:app"; Port = 8013 },
    @{ Name = "supplier_c"; Module = "agents.supplier_c.main:app"; Port = 8014 },
    @{ Name = "logistics";  Module = "agents.logistics.main:app";  Port = 8015 },
    @{ Name = "buyer_a";    Module = "agents.buyer_a.main:app";    Port = 8010 },
    @{ Name = "buyer_b";    Module = "agents.buyer_b.main:app";    Port = 8012 }
)

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null

foreach ($p in $procs) {
    Write-Host ("启动 {0} :{1}" -f $p.Name, $p.Port)
    Start-Process -FilePath $Py `
        -ArgumentList "-m","uvicorn",$p.Module,"--host","127.0.0.1","--port",$p.Port `
        -WorkingDirectory $Root `
        -WindowStyle Minimized
    Start-Sleep -Milliseconds 400
}

Write-Host ""
Write-Host "全部已拉起。验证："
Write-Host "  .\.venv\Scripts\python.exe scripts\smoke_all_local.py"
Write-Host "UI："
Write-Host "  .\scripts\start_ui_local.ps1"
