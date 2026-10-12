@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
    python skill_src\chinese-forum-sentiment\scripts\stock_sentiment_scanner.py BIDU
) else (
    python skill_src\chinese-forum-sentiment\scripts\stock_sentiment_scanner.py %*
)
pause
