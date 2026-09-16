@echo off
setlocal
rem Change to repository root if needed
cd /d "%~dp0"
python "skill_src\leasehackr-ev-deals\scripts\leasehackr_ev_scraper.py"
