# 停止本机 AgentLink 相关 python/uvicorn（按端口）
$ErrorActionPreference = "SilentlyContinue"
$ports = 8010,8011,8012,8013,8014,8015,8080,8090,8091,8092,8093,8094,8095
foreach ($p in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if ($c.OwningProcess) {
            Write-Host "停止端口 $p PID $($c.OwningProcess)"
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}
Write-Host "完成。"
