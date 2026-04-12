@echo off
echo Starting NSFW UI...
REM Redirecting stdout and stderr to nsfw_crash_log.txt
python nsfw_ui.py > nsfw_crash_log.txt 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application crashed with exit code %ERRORLEVEL%. 
    echo Please check nsfw_crash_log.txt for details.
    pause
)
