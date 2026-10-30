$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
uv run uvicorn agents.supplier_a.main:app --host 0.0.0.0 --port 8011
