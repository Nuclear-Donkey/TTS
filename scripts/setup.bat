@echo off
REM Windows setup for voice-input.
REM
REM Run this ONCE from the project root (double-click or PowerShell):
REM   scripts\setup.bat
REM
REM Creates .venv\, installs dependencies, downloads the Paraformer model.
REM Does NOT need admin rights (but running the app later does).

setlocal ENABLEEXTENSIONS

pushd "%~dp0\.."
set PROJECT_ROOT=%CD%

echo === voice-input-win setup ===
echo Project root: %PROJECT_ROOT%
echo.

REM ---- 1. Check Python ----
py -3 --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python 3.10+ not found.
        echo Install from https://www.python.org/downloads/ then re-run this script.
        exit /b 1
    )
    set PY_CMD=python
) else (
    set PY_CMD=py -3
)
echo Using: %PY_CMD%
%PY_CMD% --version

REM ---- 2. Create venv ----
if not exist .venv (
    echo Creating .venv ...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :err
)

REM ---- 3. Install deps ----
echo Installing Python deps ^(sherpa-onnx, sounddevice, keyboard, pyperclip^) ...
.venv\Scripts\python -m pip install --upgrade pip --quiet
if errorlevel 1 goto :err
.venv\Scripts\python -m pip install ^
    sherpa-onnx ^
    numpy ^
    sounddevice ^
    keyboard ^
    pyperclip ^
    --quiet
if errorlevel 1 goto :err

REM ---- 4. Editable install so `python -m voice_input_win` works ----
.venv\Scripts\python -m pip install -e . --quiet
if errorlevel 1 goto :err

REM ---- 5. Seed default config ----
set CFG_DIR=%APPDATA%\voice-input
set CFG_FILE=%CFG_DIR%\config.toml
if not exist "%CFG_FILE%" (
    if not exist "%CFG_DIR%" mkdir "%CFG_DIR%"
    copy /Y resources\default-config-win.toml "%CFG_FILE%" >nul
    echo Seeded default config: %CFG_FILE%
)

REM ---- 6. Model ----
set MODEL_DIR=%LOCALAPPDATA%\voice-input\models\paraformer-zh
if not exist "%MODEL_DIR%\model.int8.onnx" (
    echo Downloading Paraformer model ^(~80MB, one-time^) ...
    .venv\Scripts\python scripts\download_model_win.py --small
    if errorlevel 1 goto :err
) else (
    echo Model already present at %MODEL_DIR%
)

echo.
echo === Setup complete ===
echo.
echo Next: start the app by running:
echo    scripts\run-as-admin.bat
echo.
echo Then hold Right Alt in any text field to dictate.
popd
exit /b 0

:err
echo.
echo Setup FAILED. See error above.
popd
exit /b 1
