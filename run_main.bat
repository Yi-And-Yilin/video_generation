@echo off
setlocal
cd /d %~dp0

if "%1"=="silent" goto :run

echo Set WshShell = CreateObject("WScript.Shell") > %temp%\run_main_hidden.vbs
echo WshShell.Run """%~f0"" silent", 0, False >> %temp%\run_main_hidden.vbs
wscript %temp%\run_main_hidden.vbs
del %temp%\run_main_hidden.vbs
exit /b

:run
REM Redirecting stdout and stderr to main_crash_log.txt
pythonw main_ui.py > main_crash_log.txt 2>&1
