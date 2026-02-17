#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

source .venv/bin/activate

export PT_CREDS_PATH="$HOME/.secrets/property-tracker-creds.json"
export PT_SPREADSHEET_ID="1gdnnmodlkR8CzNAhXfKP90T_VBpnkSQVKvJ2ezjDOX8"

python3 run.py
