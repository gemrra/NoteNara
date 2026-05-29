@echo off
cd /d %~dp0
call venv\Scripts\activate.bat
start "" pythonw meeting_app.py
exit
