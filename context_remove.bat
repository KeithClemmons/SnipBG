@echo off
REM Wrapper invoked by the Explorer right-click menu. %1 = the selected file.
cd /d "%~dp0"
set "OUT=%USERPROFILE%\Downloads\background-remover-output"
echo Removing background from: %~nx1
call .venv\Scripts\python cli.py "%~1" -o "%OUT%"
echo.
echo Saved to %OUT%
start "" "%OUT%"
timeout /t 3 >nul
