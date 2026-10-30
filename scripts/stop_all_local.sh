#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ports=(8010 8011 8012 8013 8014 8015 8080 8090 8091 8092 8093 8094 8095)
for p in "${ports[@]}"; do
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${p}/tcp" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -t -iTCP:"$p" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "${pids}" ]]; then
      kill -9 $pids 2>/dev/null || true
      echo "stopped :$p"
    fi
  fi
done
# pid files
if [[ -d logs ]]; then
  for f in logs/*.pid; do
    [[ -f "$f" ]] || continue
    kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  done
fi
echo "完成。"
