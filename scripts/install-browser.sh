#!/usr/bin/env bash
# Optional browser collector. The API batch still runs if this is skipped:
# enabled web attempts are stored as browser_unavailable instead of crashing.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

python3 -m pip install -e "services/data-collectors[browser]"
python3 -m playwright install chromium

echo "Playwright Chromium is installed."
echo "Optional Camoufox: python3 -m pip install camoufox && export GEO_BROWSER_ENGINE=camoufox"
echo "If Camoufox cannot be imported, collection falls back to Chromium."
echo "Proxy: export GEO_BROWSER_PROXY=http://127.0.0.1:7890"
