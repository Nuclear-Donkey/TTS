# PyInstaller spec for voice-input-win (single-file, windowed).
#
# Run on a Windows machine (with the same Python + venv used during dev):
#     .venv\Scripts\pyinstaller voice-input-win.spec
#
# Output:  dist\voice-input.exe   (single file, ~180-220 MB)
#
# Requires:
#   pip install pyinstaller PySide6 sherpa-onnx sounddevice keyboard pyperclip numpy

# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_dynamic_libs,
    collect_data_files,
    collect_submodules,
)

PROJECT = Path(SPECPATH)

# --- Binary deps that PyInstaller can't auto-detect ---
binaries = []
binaries += collect_dynamic_libs("sherpa_onnx")
binaries += collect_dynamic_libs("sounddevice")  # portaudio dll

# --- Data files ---
datas = [
    (str(PROJECT / "resources" / "default-config-win.toml"), "resources"),
    (str(PROJECT / "resources" / "icons" / "voice-input.ico"), "resources/icons"),
]

# sherpa-onnx sometimes ships config jsons next to its .pyd — grab them too
datas += collect_data_files("sherpa_onnx")

hiddenimports = []
hiddenimports += collect_submodules("sherpa_onnx")
# PySide6 uses shiboken6 for its C++ bindings
hiddenimports += ["shiboken6"]

a = Analysis(
    [str(PROJECT / "src" / "voice_input_win" / "__main__.py")],
    pathex=[str(PROJECT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Drop heavyweights we don't use
        "tkinter",
        "matplotlib",
        "PIL",
        "scipy",
        "pandas",
        "IPython",
        "pytest",
        # Linux/mac-only siblings
        "voice_ibus",
        "voice_input_macos",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="voice-input",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # UPX can trigger AV false-positives, skip
    console=False,    # <<< GUI app, no terminal window
    windowed=True,
    icon=str(PROJECT / "resources" / "icons" / "voice-input.ico"),
    onefile=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
