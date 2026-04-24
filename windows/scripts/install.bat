@echo off
REM ============================================================
REM  voice-input-win 一键安装 + 编译 + 快捷方式
REM
REM  只需双击本文件一次,自动做完:
REM    1. 检查 Python (3.10 ~ 3.13)
REM    2. 建 .venv 并装所有运行时依赖 (sherpa-onnx + PySide6 + ...)
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
REM If an existing .venv uses a different Python version than the one
REM we just picked, we rebuild to stay in sync with the host.
set "VENV_PY=.venv\Scripts\python"
set "REBUILD_VENV=0"

if exist .venv (
    for /f "usebackq tokens=2" %%v in (`%VENV_PY% --version 2^>^&1`) do set "VENV_VER=%%v"
    for /f "usebackq tokens=2" %%v in (`%PY_CMD% --version 2^>^&1`) do set "HOST_VER=%%v"
    echo      existing .venv Python: !VENV_VER!
    echo      host Python:           !HOST_VER!
    if not "!VENV_VER!"=="!HOST_VER!" (
        echo      versions differ - rebuilding .venv
        set "REBUILD_VENV=1"
    )
) else (
    set "REBUILD_VENV=1"
)

if "!REBUILD_VENV!"=="1" (
    echo [2/5] Creating .venv with %PY_CMD% ...
    if exist .venv rmdir /s /q .venv
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo [2/5] Reusing existing .venv
)

REM ---- 2b. Sync shared/ from the repo root into src\shared ----
REM The shared package lives one level up in <repo>\shared; pip install -e .
REM only picks up packages under windows\src, so we mirror it here.
REM (Added to .gitignore to avoid double-tracking.)
set "SHARED_SRC=%PROJECT_ROOT%\..\shared"
set "SHARED_DST=%PROJECT_ROOT%\src\shared"
if not exist "%SHARED_SRC%" (
    echo ERROR: shared/ not found at %SHARED_SRC%.
    echo Make sure you cloned the full repo, not just windows/.
    goto :fail
)
if exist "%SHARED_DST%" rmdir /s /q "%SHARED_DST%"
xcopy /e /i /q /y "%SHARED_SRC%" "%SHARED_DST%" >nul
if errorlevel 1 goto :fail

REM ---- 3. Runtime + build deps in one shot ----
echo [3/5] Installing dependencies ^(this takes a few minutes^) ...
%VENV_PY% -m pip install --upgrade pip wheel --quiet
if errorlevel 1 goto :fail

REM Runtime + build deps combined. PySide6 (official Qt for Python)
REM has reliable wheels across Python 3.9-3.13, unlike PyQt6 which
REM sometimes falls back to from-source builds needing the Qt SDK.
%VENV_PY% -m pip install --only-binary=:all: ^
    sherpa-onnx ^
    numpy ^
    sounddevice ^
    keyboard ^
    pyperclip ^
    "PySide6>=6.6" ^
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

REM ---- Desktop shortcut (always recreate so new icon takes effect) ----
set "EXE=%PROJECT_ROOT%\dist\voice-input.exe"
set "LNK=%USERPROFILE%\Desktop\voice-input.lnk"

echo Creating desktop shortcut ...
if exist "%LNK%" del /q "%LNK%"
powershell -NoProfile -Command ^
    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%');" ^
    "$s.TargetPath='%EXE%';" ^
    "$s.WorkingDirectory='%PROJECT_ROOT%\dist';" ^
    "$s.IconLocation='%EXE%,0';" ^
    "$s.Save()"

REM ---- Clear Windows icon cache so the new .ico is picked up ----
REM Explorer caches shortcut icons aggressively; without this, users
REM see the previous icon until a reboot.
echo Clearing Windows icon cache ...
taskkill /f /im explorer.exe >nul 2>&1
del /f /q "%LOCALAPPDATA%\IconCache.db" >nul 2>&1
del /f /q "%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db" >nul 2>&1
del /f /q "%LOCALAPPDATA%\Microsoft\Windows\Explorer\thumbcache_*.db" >nul 2>&1
start explorer.exe

echo.
echo ============================================================
echo   DONE.
echo ============================================================
echo   Executable:   %EXE%
echo   Desktop:      %LNK%
echo.
echo   Double-click the desktop "voice-input" icon to launch.
echo   Hold [Caps Lock] in any text box to dictate.
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
