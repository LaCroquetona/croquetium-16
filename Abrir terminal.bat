@echo off
cd /d "%~dp0"
where py >/dev/null 2>/dev/null && (py -3 croquetium_terminal.py) || (python croquetium_terminal.py)
if errorlevel 1 pause
