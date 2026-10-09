@echo off
REM ===== Installs the Real-ESRGAN AI upscaler for the Enhance feature =====
REM Run setup.bat first. Without this, Enhance still works via a Lanczos fallback.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo Run setup.bat first. & pause & exit /b 1 )

echo Installing realesrgan + basicsr (this can take a few minutes)...
call .venv\Scripts\python -m pip install realesrgan basicsr
if errorlevel 1 ( echo Install failed & pause & exit /b 1 )

echo Patching basicsr for modern torchvision...
call .venv\Scripts\python fix_basicsr.py

echo Downloading model weights (~64 MB)...
if not exist "models" mkdir models
if not exist "models\RealESRGAN_x4plus.pth" (
  powershell -Command "try { Invoke-WebRequest 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth' -OutFile 'models\RealESRGAN_x4plus.pth' } catch { exit 1 }"
  if errorlevel 1 ( echo Weights download failed ^(check internet^) & pause & exit /b 1 )
)

echo.
echo Done. Tick "Enhance" in the app to use AI upscaling.
pause
