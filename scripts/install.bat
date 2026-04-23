@echo off
REM ============================================================
REM  voice-input-win 一键安装 + 编译 + 快捷方式
REM
REM  只需双击本文件一次,自动做完:
REM    1. 检查 Python (3.10 ~ 3.13)
REM    2. 建 .venv 并装所有运行时依赖 (sherpa-onnx + PyQt6 + ...)
REM    3. 下载识别模型 (~80MB)
REM    4. 装 PyInstaller 并编译出 dist\voice-input.exe
REM    5. 在桌面创建快捷方式
REM
REM  用户之后只需双击桌面的 "voice-input" 即可启动,无需终端。
REM ============================================================

setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION
pushd "%~dp0\.."

set "PROJECT_ROOT=%CD%"
echo.
echo ============================================================
echo   voice-input-win   一键安装
echo ============================================================
echo   Project:   %PROJECT_ROOT%
echo.

REM ---- 1. Python 3.10-3.13 ----
set "PY_CMD="
for %%V in (3.12 3.11 3.13 3.10) do (
    if "!PY_CMD!"=="" (
        py -%%V --version >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD=py -%%V"
            echo [1/5] Using Python %%V
        )
    )
)
if "!PY_CMD!"=="" (
    python --version >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=python"
        echo [1/5] Using default python
        python --version
    )
)
if "!PY_CMD!"=="" (
    echo.
    echo ERROR: Python 3.10-3.13 not found.
    echo Install from https://www.python.org/downloads/
    echo and check "Add Python to PATH" during install.
    goto :fail
)

REM ---- 2. venv ----
if not exist .venv (
    echo [2/5] Creating .venv ...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo [2/5] Reusing existing .venv
)

set "VENV_PY=.venv\Scripts\python"

REM ---- 3. Runtime + build deps in one shot ----
echo [3/5] Installing dependencies ^(this takes a few minutes^) ...
%VENV_PY% -m pip install --upgrade pip wheel --quiet
if errorlevel 1 goto :fail

REM Runtime + build deps combined. PyQt6 pinned to 6.7.x so wheels
REM resolve on Python 3.13 (6.11 has no 3.13 wheels).
%VENV_PY% -m pip install ^
    sherpa-onnx ^
    numpy ^
    sounddevice ^
    keyboard ^
    pyperclip ^
    "PyQt6>=6.6,<6.8" ^
    Pillow ^
    pyinstaller ^
    pywin32 ^
    --quiet
if errorlevel 1 (
    echo.
    echo Install failed. Common causes:
    echo   - No internet / blocked PyPI. Try:
    echo       %VENV_PY% -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple ...
    echo   - Python version mismatch. Need 3.10-3.13.
    goto :fail
)

REM ---- 4. Model + default config ----
echo [4/5] Preparing model and config ...

set "CFG_DIR=%APPDATA%\voice-input"
set "CFG_FILE=%CFG_DIR%\config.toml"
if not exist "%CFG_FILE%" (
    if not exist "%CFG_DIR%" mkdir "%CFG_DIR%"
    copy /Y resources\default-config-win.toml "%CFG_FILE%" >nul
    echo      seeded config: %CFG_FILE%
)

set "MODEL_DIR=%LOCALAPPDATA%\voice-input\models\paraformer-zh"
if not exist "%MODEL_DIR%\tokens.txt" (
    echo      downloading Paraformer-zh model ^(~80MB^) ...
    %VENV_PY% scripts\download_model_win.py --small
    if errorlevel 1 goto :fail
) else (
    echo      model already present
)

REM ---- 5. Editable install + icon + build exe ----
echo [5/5] Compiling voice-input.exe ...
%VENV_PY% -m pip install -e . --quiet
if errorlevel 1 goto :fail

%VENV_PY% scripts\generate_icon.py
if errorlevel 1 goto :fail

if exist build rmdir /s /q build
if exist dist\voice-input.exe del /q dist\voice-input.exe
.venv\Scripts\pyinstaller voice-input-win.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo PyInstaller failed. See output above.
    goto :fail
)

REM ---- Desktop shortcut ----
set "EXE=%PROJECT_ROOT%\dist\voice-input.exe"
set "LNK=%USERPROFILE%\Desktop\voice-input.lnk"

echo Creating desktop shortcut ...
powershell -NoProfile -Command ^
    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%');" ^
    "$s.TargetPath='%EXE%';" ^
    "$s.WorkingDirectory='%PROJECT_ROOT%\dist';" ^
    "$s.IconLocation='%EXE%';" ^
    "$s.Save()"

echo.
echo ============================================================
echo   DONE.
echo ============================================================
echo   Executable:   %EXE%
echo   Desktop:      %LNK%
echo.
echo   Double-click the desktop "voice-input" icon to launch.
echo   Hold [right alt] in any text box to dictate.
echo ============================================================
echo.
pause
popd
exit /b 0

:fail
echo.
echo ============================================================
echo   Install failed. See errors above.
echo ============================================================
pause
popd
exit /b 1
