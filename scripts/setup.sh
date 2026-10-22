#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install \
  -e "services/analysis-engine[dev]" \
  -e "services/data-collectors[dev]" \
  -e "services/api[dev]"

echo "SAG MVP development environment is ready."
