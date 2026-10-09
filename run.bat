@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First-time setup needed. Running setup.bat...
  call setup.bat
)
call .venv\Scripts\pythonw app.py
