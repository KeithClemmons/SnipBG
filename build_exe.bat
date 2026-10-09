@echo off
REM ===== Optional: build a standalone SnipBG.exe you can pin to the taskbar =====
REM Run setup.bat first. The .exe will appear in the dist\ folder.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo Run setup.bat first. & pause & exit /b 1 )

call .venv\Scripts\python -m pip install pyinstaller
call .venv\Scripts\python -m PyInstaller --noconfirm --windowed --onedir ^
  --name SnipBG --icon snipbg.ico app.py

echo.
echo Done. Find SnipBG.exe in: dist\SnipBG\
echo Right-click it -> Pin to taskbar.
pause
