#Requires -Version 5.1
<#
.SYNOPSIS
  打包可一键部署的干净发布压缩包（不含密钥、截图、.venv、双云私货）
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root

$Stamp = Get-Date -Format "yyyyMMdd_HHmm"
$OutDir = Join-Path $Root "release"
$Stage = Join-Path $OutDir ("agentlink_" + $Stamp)
$ZipPath = Join-Path $OutDir ("agentlink_local_deploy_" + $Stamp + ".zip")

# --- ensure vendor ---
$Vendor = Join-Path $Root "vendor"
New-Item -ItemType Directory -Force -Path $Vendor | Out-Null
$AcpsSrc = "f:\code\智能体协议\ACPs-community\acps-sdk"
$WitSrc = "f:\code\智能体协议\wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl"
$AcpsDst = Join-Path $Vendor "acps-sdk"
$WitDst = Join-Path $Vendor "wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl"

if (-not (Test-Path $AcpsDst)) {
    if (-not (Test-Path $AcpsSrc)) { throw "找不到 acps-sdk: $AcpsSrc" }
    Write-Host "==> Copy vendor/acps-sdk ..."
    robocopy $AcpsSrc $AcpsDst /E /XD .git __pycache__ .pytest_cache .venv /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
}
if (-not (Test-Path $WitDst)) {
    if (-not (Test-Path $WitSrc)) { throw "找不到 wit wheel: $WitSrc" }
    Write-Host "==> Copy wit wheel ..."
    Copy-Item $WitSrc $WitDst -Force
}

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$IncludeDirs = @(
    "acs",
    "agents",
    "agentlink_runtime",
    "commerce",
    "commerce_v2",
    "config",
    "tests",
    "ui",
    "vendor",
    "java-suppliers"
)

Write-Host "==> Staging source trees ..."
foreach ($d in $IncludeDirs) {
    $src = Join-Path $Root $d
    if (-not (Test-Path $src)) { continue }
    $dst = Join-Path $Stage $d
    if ($d -eq "java-suppliers") {
        robocopy $src $dst /E /XD .tools .gradle build .git __pycache__ /XF *.jar *.class /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    } else {
        robocopy $src $dst /E /XD __pycache__ .pytest_cache .git .venv /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    }
}

# scripts whitelist
$ScriptNames = @(
    "bootstrap_local.ps1", "bootstrap_local.sh",
    "start_all_local.ps1", "start_all_local.sh",
    "start_ui_local.ps1", "start_ui_local.sh",
    "start_ui_domains.ps1",
    "stop_all_local.ps1", "stop_all_local.sh",
    "smoke_all_local.py", "smoke_local.py", "smoke_wit_llm.py",
    "pack_release.ps1", "enroll_platform.py"
)
$ScriptsDst = Join-Path $Stage "scripts"
New-Item -ItemType Directory -Force -Path $ScriptsDst | Out-Null
foreach ($n in $ScriptNames) {
    $p = Join-Path $Root "scripts\$n"
    if (Test-Path $p) { Copy-Item $p (Join-Path $ScriptsDst $n) -Force }
}

# docs: keep markdown / asbuilt, skip heavy evidence media
Write-Host "==> Staging docs (markdown only) ..."
$DocsDst = Join-Path $Stage "docs"
New-Item -ItemType Directory -Force -Path $DocsDst | Out-Null
$DocKeep = @(
    "commerce_v2_asbuilt.md",
    "current_tech_stack.md",
    "design_two_paths_interconnect.md",
    "README.md"
)
foreach ($n in $DocKeep) {
    $p = Join-Path $Root "docs\$n"
    if (Test-Path $p) { Copy-Item $p (Join-Path $DocsDst $n) -Force }
}
# design_report md
$Dr = Join-Path $Root "docs\design_report"
if (Test-Path $Dr) {
    $DrDst = Join-Path $DocsDst "design_report"
    New-Item -ItemType Directory -Force -Path $DrDst | Out-Null
    Get-ChildItem $Dr -Filter "*.md" | Copy-Item -Destination $DrDst -Force
}
# interaction contract already under commerce_v2

# root files
$RootFiles = @(
    ".env.example", ".gitignore", "AGENTS.md", "README.md",
    "pyproject.toml", "requirements-smoke.txt", "LICENSE"
)
foreach ($n in $RootFiles) {
    $p = Join-Path $Root $n
    if (Test-Path $p) { Copy-Item $p (Join-Path $Stage $n) -Force }
}

# data placeholder
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "data") | Out-Null
Set-Content -Path (Join-Path $Stage "data\.gitkeep") -Value ""

# scrub real platform configs if copied — keep examples only
Get-ChildItem (Join-Path $Stage "config") -File -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.Name -match 'platform_aics' -and $_.Name -notmatch 'example') {
        Remove-Item $_.FullName -Force
    }
    if ($_.Name -eq "acps_platform.yaml") {
        Remove-Item $_.FullName -Force
    }
}

# one-click entry
$Quick = @"
# AgentLink 一键本地部署（Windows）

1. 解压本目录到任意路径（路径勿含奇怪权限问题即可）
2. 右键用 PowerShell 运行：

``````powershell
.\scripts\bootstrap_local.ps1
``````

3. 编辑根目录 ``.env``，把 ``LLM_API_KEY`` 换成你的 DeepSeek / OpenAI 兼容 Key
4. 启动：

``````powershell
.\scripts\start_all_local.ps1
.\scripts\start_ui_local.ps1
``````

5. 浏览器打开 http://127.0.0.1:8090

停止：``.\scripts\stop_all_local.ps1``

详细说明见 README.md
"@
Set-Content -Path (Join-Path $Stage "START_HERE.txt") -Value $Quick -Encoding UTF8

Write-Host "==> Zipping $ZipPath ..."
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path $Stage -DestinationPath $ZipPath -CompressionLevel Optimal

$size = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Host ""
Write-Host "OK stage: $Stage"
Write-Host "OK zip:   $ZipPath  ($size MB)" -ForegroundColor Green
