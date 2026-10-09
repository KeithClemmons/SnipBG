@echo off
REM Run the SnipBG command-line interface. Example:
REM   snipbg-cli photo.jpg -o output --background white
cd /d "%~dp0"
call .venv\Scripts\python cli.py %*
