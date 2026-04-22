@echo off
REM Launch voice-input-win with Administrator privileges.
REM
REM The `keyboard` library needs admin to reliably hook global hotkeys,
REM especially when the focused window itself is elevated (Task Manager,
REM some installers). Without admin, the hotkey works for most apps but
REM may silently miss events in elevated windows.

setlocal
pushd "%~dp0\.."

REM Check if already elevated
net session >nul 2>&1
if %errorlevel%==0 goto :run_app

REM Relaunch self as admin via PowerShell
echo Requesting administrator privileges...
powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
popd
exit /b 0

:run_app
if not exist .venv\Scripts\python.exe (
    echo ERROR: .venv not found. Run scripts\setup.bat first.
    pause
    exit /b 1
)

echo Starting voice-input-win ^(admin^) ...
.venv\Scripts\python -m voice_input_win
echo.
echo voice-input-win exited. Press any key to close.
pause >nul
popd
