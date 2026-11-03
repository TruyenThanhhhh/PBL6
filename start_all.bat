@echo off
chcp 65001 > nul
echo ========================================================
echo   KHOI DONG PBL6 (BACKEND 8000 + FRONTEND 5174)
echo ========================================================
echo.
start "PBL6 Backend (8000)" cmd /k ""%~dp0start_app.bat""
timeout /t 4 /nobreak > nul
start "PBL6 Frontend (5174)" cmd /k ""%~dp0start_frontend.bat""
echo Da mo 2 cua so: backend va frontend.
echo Doi backend bao "Uvicorn running" roi mo http://localhost:5174
pause
