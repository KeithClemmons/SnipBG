@echo off
REM ===== SnipBG one-time setup =====
REM Creates a local Python virtual environment and installs everything.
cd /d "%~dp0"

REM --- Pick a good Python interpreter ---
REM Prefer the py launcher targeting 3.11, then 3.10. Fall back to plain python.
set "PY="
py -3.11 -c "import sys" >nul 2>nul && set "PY=py -3.11"
if not defined PY ( py -3.10 -c "import sys" >nul 2>nul && set "PY=py -3.10" )
if not defined PY ( where python >nul 2>nul && set "PY=python" )

if not defined PY (
  echo.
  echo No suitable Python found. Install Python 3.10 or 3.11 from
  echo https://www.python.org/downloads/ ^(tick "Add Python to PATH"^), then retry.
  echo.
  pause
  exit /b 1
)

echo Using interpreter: %PY%
%PY% -c "import sys; print(sys.version)"

echo Creating virtual environment (.venv)...
REM --without-pip avoids the ensurepip step that can crash; we bootstrap pip next.
%PY% -m venv .venv --without-pip
if errorlevel 1 ( echo Failed to create venv & pause & exit /b 1 )

echo Bootstrapping pip...
call .venv\Scripts\python -m pip --version >nul 2>nul
if errorlevel 1 (
  echo Downloading get-pip.py...
  powershell -Command "try { Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile get-pip.py } catch { exit 1 }"
  if errorlevel 1 ( echo Could not download get-pip.py ^(check internet^) & pause & exit /b 1 )
  call .venv\Scripts\python get-pip.py
  if errorlevel 1 ( echo pip bootstrap failed. & pause & exit /b 1 )
  del get-pip.py >nul 2>nul
)

echo Installing PyTorch (CPU) and dependencies. This can take several minutes...
call .venv\Scripts\python -m pip install --upgrade pip
call .venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
call .venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 ( echo Install failed & pause & exit /b 1 )

echo.
echo Setup complete. Launch with run.bat (or SnipBG.vbs for no console window).
pause
