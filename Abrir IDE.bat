@echo off
cd /d "%~dp0"
where py >/dev/null 2>/dev/null && (py -3 croquetium_ide.py) || (python croquetium_ide.py)
if errorlevel 1 pause
