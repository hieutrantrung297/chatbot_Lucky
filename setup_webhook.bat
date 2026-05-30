@echo off
cd /d "%~dp0"
echo Setting up Facebook webhook...
venv\Scripts\python.exe scripts/setup_webhook.py
pause
