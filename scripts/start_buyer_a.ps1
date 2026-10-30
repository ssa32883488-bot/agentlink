$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$env:SUPPLIER_A_RPC_URL = if ($env:SUPPLIER_A_RPC_URL) { $env:SUPPLIER_A_RPC_URL } else { "http://127.0.0.1:8011/rpc" }
uv run uvicorn agents.buyer_a.main:app --host 0.0.0.0 --port 8010
