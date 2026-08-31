#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

python_bin="${PYTHON:-python3}"
if [[ ! -d .venv ]]; then
  "$python_bin" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/pyinstaller --noconfirm --clean DDTool-macos.spec

rm -f "dist/豆荚工具.dmg"
hdiutil create \
  -volname "豆荚工具" \
  -srcfolder "dist/豆荚工具.app" \
  -ov \
  -format UDZO \
  "dist/豆荚工具.dmg"

echo "Built dist/豆荚工具.app and dist/豆荚工具.dmg"
