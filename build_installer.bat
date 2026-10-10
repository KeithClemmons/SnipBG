@echo off
REM ===== Build everything needed for a GitHub release =====
REM   1. Builds dist\SnipBG\ with PyInstaller
REM   2. Self-tests the .exe on a clean user profile (catches missing bundled files)
REM   3. Writes installer\SnipBG-<version>-windows-portable.zip
REM   4. Writes installer\SnipBG-Setup-<version>.exe  (needs Inno Setup 6:
REM        winget install JRSoftware.InnoSetup)
REM The version comes from APP_VERSION in app.py.
setlocal
cd /d "%~dp0"
REM Pausing keeps the window open when double-clicked; skipped on CI or with "nopause".
set "PAUSE=pause"
if /i "%~1"=="nopause" set "PAUSE=ver>nul"
if defined CI set "PAUSE=ver>nul"

for /f %%v in ('.venv\Scripts\python -c "import app;print(app.APP_VERSION)"') do set "VER=%%v"
if not defined VER ( echo Could not read APP_VERSION from app.py & %PAUSE% & exit /b 1 )
echo Building SnipBG %VER%

call "%~dp0build_exe.bat" nopause || exit /b 1

echo.
echo Self-testing the packaged app on a clean profile...
set "TESTHOME=%TEMP%\snipbg_selftest"
if exist "%TESTHOME%" rmdir /s /q "%TESTHOME%"
mkdir "%TESTHOME%\.transparent-background"
REM Reuse the downloaded model weights (if any) so the test doesn't re-download them,
REM but deliberately leave out config.yaml so the bundled copy gets used.
if exist "%USERPROFILE%\.transparent-background\ckpt_base.pth" copy /y "%USERPROFILE%\.transparent-background\ckpt_base.pth" "%TESTHOME%\.transparent-background\" >nul
set "REALHOME=%USERPROFILE%"
set "USERPROFILE=%TESTHOME%"
set "SNIPBG_SELFTEST=%~dp0snipbg.png|%TESTHOME%\out"
start "" /wait "dist\SnipBG\SnipBG.exe"
set "RC=%errorlevel%"
set "USERPROFILE=%REALHOME%"
set "SNIPBG_SELFTEST="
if not "%RC%"=="0" (
  echo SELF-TEST FAILED. Details:
  type "%TESTHOME%\out\selftest_error.txt"
  %PAUSE% & exit /b 1
)
if not exist "%TESTHOME%\out\selftest.png" ( echo SELF-TEST FAILED: no output written. & %PAUSE% & exit /b 1 )
echo Self-test passed.
rmdir /s /q "%TESTHOME%"

if not exist installer mkdir installer
echo.
echo Zipping portable build...
if exist "installer\SnipBG-%VER%-windows-portable.zip" del "installer\SnipBG-%VER%-windows-portable.zip"
tar -a -cf "installer\SnipBG-%VER%-windows-portable.zip" -C dist SnipBG || ( echo Zip failed & %PAUSE% & exit /b 1 )

echo.
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo Inno Setup not found, so no installer was built. Install it with:
  echo   winget install JRSoftware.InnoSetup
  %PAUSE% & exit /b 1
)
echo Building installer (compression takes a few minutes)...
"%ISCC%" /Q /DMyAppVersion=%VER% installer.iss || ( echo Installer build failed & %PAUSE% & exit /b 1 )

echo.
echo Release files are in the installer\ folder:
dir /b installer
%PAUSE%
