@echo off
setlocal
rem Change to repository root if needed
cd /d "%~dp0"
python "skill_src\leasehackr-ev-deals\scripts\pnd_ev_deals_tracker.py"
