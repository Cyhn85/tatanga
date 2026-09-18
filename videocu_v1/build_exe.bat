@echo off
REM VIDEOCU v1 - EXE Build Script
REM Windows batch file to build standalone executable

echo ================================================================
echo VIDEOCU v1 - EXE BUILD SYSTEM
echo ================================================================

REM Check if venv exists
if not exist venv (
    echo [ERROR] Virtual environment not found!
    echo [INFO] Run: python -m venv venv
    exit /b 1
)

echo [1/5] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [2/5] Installing PyInstaller...
pip install pyinstaller==6.3.0

echo.
echo [3/5] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist VIDEOCU_v1.spec del VIDEOCU_v1.spec

echo.
echo [4/5] Building EXE with PyInstaller...
echo [INFO] This may take 5-10 minutes...
echo [INFO] Output will be in dist/VIDEOCU_v1.exe

pyinstaller videocu.spec

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    exit /b 1
)

echo.
echo [5/5] Verifying build...
if exist dist\VIDEOCU_v1.exe (
    echo [OK] EXE created successfully!
    echo [FILE] dist\VIDEOCU_v1.exe

    REM Get file size
    for %%A in (dist\VIDEOCU_v1.exe) do (
        set size=%%~zA
        set /a size_mb=%%~zA/1024/1024
    )

    echo [SIZE] !size_mb! MB

    echo.
    echo ================================================================
    echo BUILD COMPLETE!
    echo ================================================================
    echo.
    echo [OUTPUT] dist\VIDEOCU_v1.exe
    echo.
    echo [NEXT STEPS]
    echo 1. Test the EXE: dist\VIDEOCU_v1.exe
    echo 2. Create .env file with your API keys
    echo 3. Add client_secrets.json for YouTube upload
    echo.
    echo [DISTRIBUTE]
    echo - EXE is portable, can run on any Windows PC
    echo - Users need to add their own .env and client_secrets.json
    echo - FFmpeg is bundled via imageio-ffmpeg
    echo.

) else (
    echo [ERROR] EXE file not found in dist/
    exit /b 1
)

pause
