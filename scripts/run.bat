@echo off
REM Launch without requesting admin. Works for 95% of apps — but global
REM hotkey may not fire when an UAC-elevated window has focus. If the
REM hotkey seems to work sometimes but not others, use run-as-admin.bat.

setlocal
pushd "%~dp0\.."

if not exist .venv\Scripts\python.exe (
    echo ERROR: .venv not found. Run scripts\setup.bat first.
    pause
    exit /b 1
)

.venv\Scripts\python -m voice_input_win
popd
