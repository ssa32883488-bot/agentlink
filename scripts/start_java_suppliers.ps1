# 启动三家 Java 供应商（8011 / 8013 / 8014）。需 JDK 17+。
$ErrorActionPreference = "Stop"
$jdk = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
if (Test-Path $jdk) {
    $env:JAVA_HOME = $jdk
    $env:Path = "$env:JAVA_HOME\bin;" + $env:Path
}
$agentlink = Split-Path $PSScriptRoot -Parent
$base = Join-Path $agentlink "java-suppliers"
$gradle = Join-Path $env:TEMP "gradle-8.10.2\bin\gradle.bat"

$jarsReady = @(
    (Test-Path (Join-Path $base "supplier-a\build\libs\supplier-a-0.1.0.jar")),
    (Test-Path (Join-Path $base "supplier-b\build\libs\supplier-b-0.1.0.jar")),
    (Test-Path (Join-Path $base "supplier-c\build\libs\supplier-c-0.1.0.jar"))
) -notcontains $false

if (-not $jarsReady) {
    if (-not (Test-Path $gradle)) {
        throw "Missing jars and Gradle at $gradle"
    }
    Push-Location $base
    try {
        & $gradle ":supplier-a:bootJar" ":supplier-b:bootJar" ":supplier-c:bootJar" "--quiet"
    } finally {
        Pop-Location
    }
}

foreach ($p in @(8011, 8013, 8014)) {
    try {
        $c = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
    } catch {}
}

foreach ($name in @("supplier-a", "supplier-b", "supplier-c")) {
    $path = Join-Path $base "$name\build\libs\$name-0.1.0.jar"
    if (-not (Test-Path $path)) { throw "Missing jar: $path" }
    Start-Process -FilePath "java" -ArgumentList "-jar", $path -WorkingDirectory (Split-Path $path -Parent) -WindowStyle Hidden
    Write-Host "started $name"
}
Write-Host "Java suppliers up: 8011 / 8013 / 8014"
Write-Host "Smoke: py -3 scripts\smoke_java_suppliers.py"
