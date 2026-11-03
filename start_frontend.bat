@echo off
chcp 65001 > nul
echo ========================================================
echo   KHOI DONG FRONTEND KNOWLEDGE AI (http://localhost:5173)
echo ========================================================
echo.
cd /d "%~dp0\sourcecode\frontend"
if not exist node_modules (
  echo Dang cai dat npm packages...
  npm install
)
npm run dev
pause
