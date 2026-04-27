@echo off
setlocal

echo Checking Blink DVR processes...

REM --- Start the clip poller if not running ---
tasklist /V /FI "IMAGENAME eq python.exe" 2>nul | findstr /C:"BlinkDVR" >nul
if errorlevel 1 (
    echo   Starting clip poller...
    start "BlinkDVR" /MIN cmd /k "cd /d C:\BlinkDVR && call venv\Scripts\activate && python blink_dvr.py"
) else (
    echo   Clip poller already running.
)

REM --- Start the web dashboard if not running ---
tasklist /V /FI "IMAGENAME eq python.exe" 2>nul | findstr /C:"BlinkWeb" >nul
if errorlevel 1 (
    echo   Starting web dashboard...
    start "BlinkWeb" /MIN cmd /k "cd /d C:\BlinkDVR && call venv\Scripts\activate && python web_app.py"
) else (
    echo   Web dashboard already running.
)

REM --- Wait for Flask to come up, then open browser ---
echo   Waiting for web server to be ready...
timeout /t 4 /nobreak >nul
start http://localhost:5000

echo Done.
endlocal