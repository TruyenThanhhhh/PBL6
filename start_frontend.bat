@echo off
chcp 65001 > nul
echo ========================================================
echo   KHOI DONG FRONTEND KNOWLEDGE AI (http://localhost:5174)
echo ========================================================
echo.
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/v1/status' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo [CANH BAO] Backend chua chay o cong 8000.
  echo Hay chay start_app.bat hoac start_all.bat truoc khi dang nhap/dang ky.
  echo.
)
cd /d "%~dp0\sourcecode\frontend"
if not exist node_modules (
  echo Dang cai dat npm packages...
  npm install
)
npm run dev
pause
