@echo off
REM Removes the SnipBG right-click menu entries.
for %%E in (png jpg jpeg webp bmp tiff gif) do (
  reg delete "HKCU\Software\Classes\SystemFileAssociations\.%%E\shell\SnipBG" /f >nul 2>nul
  echo   removed .%%E
)
echo.
echo Uninstalled.
pause
