@echo off
echo ============================================
echo  Meeting Transcriber - Install Dependencies
echo ============================================
echo.

if not exist venv\ (
    echo Creating venv...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing from requirements.txt...
pip install -r requirements.txt

echo.
echo ============================================
echo  Done. Run: Meeting_Transcriber.bat
echo ============================================
pause
