@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3 croquetium_ide.py) || (python croquetium_ide.py)
if errorlevel 1 pause
