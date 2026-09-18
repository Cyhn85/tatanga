@echo off
echo ========================================
echo TATANGA - Telegram Bot Baslatiliyor
echo ========================================
echo.

cd /d "%~dp0"

REM Check if venv exists
if not exist "venv" (
    echo Virtual environment olusturuluyor...
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate
)

echo.
echo Bot baslatiliyor...
echo Durdurmak icin Ctrl+C basin
echo.

python telegram_bot\bot.py

pause
