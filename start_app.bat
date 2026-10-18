@echo off
chcp 65001 > nul
echo ========================================================
echo   KHOI DONG PERSONAL AI KNOWLEDGE PLATFORM (PBL6 MVP)
echo ========================================================
echo.
cd /d "%~dp0\sourcecode\backend"
echo Dang chay may chu tai: http://localhost:8000
python run.py
pause
