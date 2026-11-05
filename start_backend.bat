@echo off
setlocal
cd /d "%~dp0backend"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if not exist .env (
  copy .env.example .env >nul
  echo Created backend\.env. Configure your model/provider settings, then run this script again.
  pause
  exit /b 0
)
python office_server.py
pause
