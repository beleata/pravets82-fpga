@echo off
cd /d "%~dp0"
start "" pythonw host\app.py --port COM7
if errorlevel 1 pause
