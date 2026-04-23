@echo off
REM Build voice-input.exe on Windows.
REM
REM Assumes you already ran setup.bat so .venv is populated with runtime deps.
REM This additionally installs PyInstaller + PySide6 then compiles.

setlocal ENABLEEXTENSIONS
pushd "%~dp0\.."

if not exist .venv (
    echo ERROR: .venv not found. Run scripts\setup.bat first.
    exit /b 1
)

echo === Installing build-time deps ===
.venv\Scripts\python -m pip install --upgrade pip --quiet
if errorlevel 1 goto :err
.venv\Scripts\python -m pip install --only-binary=:all: pyinstaller "PySide6>=6.6" Pillow --quiet
if errorlevel 1 goto :err

echo === Regenerating app icon ===
.venv\Scripts\python scripts\generate_icon.py
if errorlevel 1 goto :err

echo === Running PyInstaller ===
if exist build rmdir /s /q build
if exist dist\voice-input.exe del /q dist\voice-input.exe
.venv\Scripts\pyinstaller voice-input-win.spec --clean --noconfirm
if errorlevel 1 goto :err

echo.
echo === Build complete ===
echo Output: %CD%\dist\voice-input.exe
echo.
echo Double-click to run. On first launch it will download the STT model (~80MB).
popd
exit /b 0

:err
echo.
echo Build FAILED.
popd
exit /b 1
