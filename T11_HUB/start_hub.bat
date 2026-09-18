@echo off
title TATANGA Hub - Komuta Merkezi
echo.
echo  ================================================
echo   TATANGA T11_HUB - Komuta Merkezi
echo   http://localhost:8501
echo  ================================================
echo   Takip Listesi: 10dk'da 1 otomatik kontrol
echo   Zamanlayici: data/scheduler_settings.json
echo   Cikti: Desktop/CSS_Berlin_Output/
echo  ================================================
echo.

cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    pause
    exit /b 1
)

REM Kill any existing process on port 8501
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501" ^| findstr "LISTENING"') do (
    echo [INFO] Port 8501 mesgul, eski process sonlandiriliyor...
    curl -s -m 3 -X POST http://127.0.0.1:8501/api/admin/mark-jobs-interrupted >nul 2>&1
    taskkill /PID %%a /F >nul 2>&1
)

REM Start with system tray
echo [INFO] System Tray modunda baslatiliyor...
pythonw tatanga_launcher.pyw
if errorlevel 1 (
    echo [INFO] System Tray basarisiz, normal modda baslatiliyor...
    python app.py
)
pause
