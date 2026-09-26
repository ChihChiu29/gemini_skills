@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo Daily Skills Pipeline
echo Started at: %DATE% %TIME%
echo ========================================================

:: 1. Stock Price Analysis
echo.
echo [1/3] Running Stock Price Analysis...
call "C:\Users\ChihC\miniconda3\condabin\conda.bat" run -n p314 python "skill_src\stock-lows-analyzer\scripts\analyze_stocks.py"
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Stock Price Analysis exited with code %ERRORLEVEL%
)

:: 2. Stock Option Analysis
echo.
echo [2/3] Running Stock Option Analysis...
call "C:\Users\ChihC\miniconda3\condabin\conda.bat" run -n p314 python "skill_src\stock-lows-analyzer\scripts\analyze_options.py"
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Stock Option Analysis exited with code %ERRORLEVEL%
)

:: 3. Leasehackr EV Deals Tracker
echo.
echo [3/3] Running Leasehackr EV Deals Tracker...
call "C:\Users\ChihC\miniconda3\condabin\conda.bat" run -n p314 python "skill_src\leasehackr-ev-deals\scripts\pnd_ev_deals_tracker.py"
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Leasehackr EV Deals Tracker exited with code %ERRORLEVEL%
)

echo.
echo ========================================================
echo All daily tasks finished at: %DATE% %TIME%
echo ========================================================
endlocal
