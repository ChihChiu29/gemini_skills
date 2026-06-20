#!/usr/bin/env bash
# Change to repository root (assumes script is run from repo root)
SCRIPT_DIR="$(dirname "$0")"
cd "$SCRIPT_DIR"
python3 "skill_src/stock-lows-analyzer/scripts/analyze_stocks.py"
