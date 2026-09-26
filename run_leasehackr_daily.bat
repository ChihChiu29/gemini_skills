@echo off
setlocal
cd /d "%~dp0"

:: Ensure output directory exists for logs
if not exist "OUTPUT\leasehackr" mkdir "OUTPUT\leasehackr"

echo Running Leasehackr EV Deals Tracker...
echo Started at: %DATE% %TIME%

:: Activate conda environment p314 and execute the tracker script
call "C:\Users\ChihC\miniconda3\condabin\conda.bat" run -n p314 python "skill_src\leasehackr-ev-deals\scripts\pnd_ev_deals_tracker.py"

echo Finished at: %DATE% %TIME%
endlocal
