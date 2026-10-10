@echo off
REM ===== Build a standalone SnipBG.exe (dist\SnipBG\) with PyInstaller =====
REM Run setup.bat first. Pass "nopause" to skip the final pause (used by build_installer.bat).
cd /d "%~dp0"
set "PAUSE=pause"
if /i "%~1"=="nopause" set "PAUSE=ver>nul"
if defined CI set "PAUSE=ver>nul"
if not exist ".venv\Scripts\python.exe" ( echo Run setup.bat first. & %PAUSE% & exit /b 1 )

call .venv\Scripts\python -m pip install --quiet pyinstaller
REM Build settings (bundled data files, kornia source) live in SnipBG.spec.
call .venv\Scripts\python -m PyInstaller --noconfirm --clean SnipBG.spec
if errorlevel 1 ( echo PyInstaller build failed. & %PAUSE% & exit /b 1 )

echo.
echo Done. Find SnipBG.exe in: dist\SnipBG\
echo Right-click it and choose "Pin to taskbar".
%PAUSE%
