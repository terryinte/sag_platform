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
echo "浏览器采集是可选步骤。未安装时，已启用的网页通道会记为 browser_unavailable，不会让批次失败。"
echo "安装：./scripts/install-browser.sh"
echo "可选 Camoufox：pip install camoufox && export GEO_BROWSER_ENGINE=camoufox（失败则回退 Chromium）"
echo "代理：export GEO_BROWSER_PROXY=http://127.0.0.1:7890"
