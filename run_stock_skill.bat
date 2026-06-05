@echo off
setlocal
rem Change to repository root if needed
cd /d "%~dp0"
python "skill_src\stock-lows-analyzer\scripts\analyze_stocks.py"
