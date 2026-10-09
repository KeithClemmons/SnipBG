@echo off
REM Adds "Remove background (SnipBG)" to the right-click menu for image files.
REM Installs under HKCU (no admin needed). Run uninstall_context_menu.bat to remove.
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

call :reg png
call :reg jpg
call :reg jpeg
call :reg webp
call :reg bmp
call :reg tiff
call :reg gif

echo.
echo Installed. Right-click an image and choose "Remove background (SnipBG)".
pause
exit /b 0

:reg
set "EXT=%~1"
reg add "HKCU\Software\Classes\SystemFileAssociations\.%EXT%\shell\SnipBG" /ve /d "Remove background (SnipBG)" /f >nul
reg add "HKCU\Software\Classes\SystemFileAssociations\.%EXT%\shell\SnipBG" /v Icon /d "%DIR%\snipbg.ico" /f >nul
reg add "HKCU\Software\Classes\SystemFileAssociations\.%EXT%\shell\SnipBG\command" /ve /d "\"%DIR%\context_remove.bat\" \"%%1\"" /f >nul
echo   added .%EXT%
goto :eof
