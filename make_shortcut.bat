@echo off
REM Creates a SnipBG shortcut (with icon) on your Desktop.
REM Then right-click it -> Pin to taskbar.
cd /d "%~dp0"
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "PYW=%DIR%\.venv\Scripts\pythonw.exe"
set "LNK=%USERPROFILE%\Desktop\SnipBG.lnk"

powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%');" ^
  "$s.TargetPath='%PYW%';" ^
  "$s.Arguments='\"%DIR%\app.py\"';" ^
  "$s.WorkingDirectory='%DIR%';" ^
  "$s.IconLocation='%DIR%\snipbg.ico';" ^
  "$s.Description='SnipBG background remover';" ^
  "$s.Save()"

if exist "%LNK%" (
  echo Created shortcut on your Desktop: SnipBG
  echo Now right-click it and choose "Pin to taskbar".
) else (
  echo Could not create the shortcut.
)
pause
