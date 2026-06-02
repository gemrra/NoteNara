@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  NoteNara - Install dependencies
echo ============================================
echo.

REM 1. Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo.
    echo Install Python 3.10+ from https://www.python.org/downloads/windows/
    echo During install: tick "Add python.exe to PATH" at the bottom of the installer.
    echo Then re-run this script.
    echo.
    pause
    exit /b 1
)

REM 2. Create venv if missing
if not exist venv\ (
    echo [1/2] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] venv creation failed.
        pause
        exit /b 1
    )
) else (
    echo [1/2] venv already exists, skipping creation.
)

REM 3. Install requirements
echo.
echo [2/2] Installing requirements (this may take 5-10 minutes — CUDA libs are large)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed. Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Done. Launch the app:
echo    NoteNara.bat
echo.
echo  Or build a standalone NoteNara.exe:
echo    pip install pyinstaller pywin32
echo    python -m PyInstaller --onefile --windowed ^
echo        --icon=app\assets\NoteNara.ico --name=NoteNara ^
echo        --distpath=. --workpath=build --specpath=build ^
echo        --noconfirm launcher.py
echo ============================================
pause
