#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -x "$repo_dir/.venv/bin/uvicorn" ]]; then
  echo "Run ./scripts/setup.sh first." >&2
  exit 1
fi

cd "$repo_dir/services/api"
exec "$repo_dir/.venv/bin/uvicorn" api.main:app --host 127.0.0.1 --port 8000 --reload
