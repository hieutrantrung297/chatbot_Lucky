@echo off
cd /d "%~dp0"

echo [1/2] Starting uvicorn...
start "Lucky Bot - Server" cmd /k "venv\Scripts\activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo [2/2] Starting ngrok...
start "Lucky Bot - ngrok" cmd /k "ngrok.exe start lucky"

echo.
echo Both windows started.
echo Server : http://localhost:8000
echo Public : https://january-autolytic-meridith.ngrok-free.dev
echo.
pause
