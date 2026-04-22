#!/usr/bin/env bash
#
# Build a Windows-ready zip that users extract and run setup.bat on.
#
#   ./scripts/package-win.sh            → voice-input-win-0.1.0.zip  (~50 KB)
#   ./scripts/package-win.sh --with-model → voice-input-win-0.1.0-with-model.zip (~230 MB)
#
# Package layout inside zip:
#   voice-input-win-0.1.0/
#     ├── pyproject.toml
#     ├── README-WINDOWS.md      → renamed to README.md at top
#     ├── src/voice_input_win/   (Linux version not included)
#     ├── scripts/
#     │   ├── setup.bat
#     │   ├── run-as-admin.bat
#     │   ├── run.bat
#     │   └── download_model_win.py
#     ├── resources/
#     │   └── default-config-win.toml
#     └── bundled-model/         (only with --with-model)
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(grep -m1 '^version' "${PROJECT_ROOT}/pyproject.toml" | sed -E 's/.*"([^"]+)".*/\1/')"
WITH_MODEL=0

for arg in "$@"; do
    case "$arg" in
        --with-model) WITH_MODEL=1 ;;
        -h|--help)
            echo "Usage: $0 [--with-model]"
            exit 0
            ;;
        *) echo "Unknown: $arg"; exit 2 ;;
    esac
done

suffix=""
[[ $WITH_MODEL -eq 1 ]] && suffix="-with-model"
PKG_NAME="voice-input-win-${VERSION}${suffix}"

STAGE_ROOT="$(mktemp -d)"
trap 'rm -rf "${STAGE_ROOT}"' EXIT
STAGE="${STAGE_ROOT}/${PKG_NAME}"

echo "Staging Windows package into ${STAGE}"
mkdir -p "${STAGE}/src" "${STAGE}/scripts" "${STAGE}/resources"

# Source — only the Windows package, not voice_ibus. Strip caches.
cp -r "${PROJECT_ROOT}/src/voice_input_win" "${STAGE}/src/"
find "${STAGE}/src" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${STAGE}/src" -type f -name "*.pyc" -delete 2>/dev/null || true

# Scripts (Windows-relevant only).
cp "${PROJECT_ROOT}/scripts/setup.bat"              "${STAGE}/scripts/"
cp "${PROJECT_ROOT}/scripts/run-as-admin.bat"       "${STAGE}/scripts/"
cp "${PROJECT_ROOT}/scripts/run.bat"                "${STAGE}/scripts/"
cp "${PROJECT_ROOT}/scripts/download_model_win.py"  "${STAGE}/scripts/"

# Resources.
cp "${PROJECT_ROOT}/resources/default-config-win.toml" "${STAGE}/resources/"

# pyproject — keep as-is; setup.bat uses `pip install -e .` so the
# [project.scripts] voice-ibus entry will fail to resolve voice_ibus
# (not present). Strip Linux-only bits for cleanliness.
python3 <<PY
import re
src = open("${PROJECT_ROOT}/pyproject.toml").read()
# Drop the Linux console-script and package
src = re.sub(r'voice-ibus = "voice_ibus\.__main__:main"\n', '', src)
src = src.replace('packages = ["src/voice_ibus", "src/voice_input_win"]',
                  'packages = ["src/voice_input_win"]')
# Drop the comment about system site-packages (Linux-specific)
src = re.sub(r'\[tool\.uv\]\n.*?(?=\n\[|\Z)', '', src, flags=re.S)
open("${STAGE}/pyproject.toml", "w").write(src)
PY

# README at top level.
cp "${PROJECT_ROOT}/README-WINDOWS.md" "${STAGE}/README.md"

# Design doc for reference.
mkdir -p "${STAGE}/docs"
cp "${PROJECT_ROOT}/docs/superpowers/specs/2026-04-22-ibus-voice-input-design.md" \
   "${STAGE}/docs/original-linux-design.md"

# Optional bundled model.
if [[ $WITH_MODEL -eq 1 ]]; then
    MODEL_SRC="${HOME}/.local/share/ibus-voice/models/paraformer-zh"
    if [[ -d "${MODEL_SRC}" ]]; then
        echo "Including model from ${MODEL_SRC}..."
        mkdir -p "${STAGE}/bundled-model"
        cp "${MODEL_SRC}/model.int8.onnx" "${STAGE}/bundled-model/"
        cp "${MODEL_SRC}/tokens.txt"      "${STAGE}/bundled-model/"
        # Add a tiny shim to setup.bat so it picks up the bundled model.
        # We patch a marker in the setup.bat template; keep it simple by
        # writing an extra bat file the user runs BEFORE setup.bat.
        cat > "${STAGE}/scripts/install-bundled-model.bat" <<'BUNDLE_EOF'
@echo off
setlocal
pushd "%~dp0\.."
set MODEL_DIR=%LOCALAPPDATA%\voice-input\models\paraformer-zh
if not exist "%MODEL_DIR%" mkdir "%MODEL_DIR%"
if not exist bundled-model\model.int8.onnx (
    echo bundled-model folder not found. Is this the --with-model package?
    exit /b 1
)
copy /Y bundled-model\model.int8.onnx "%MODEL_DIR%\" >nul
copy /Y bundled-model\tokens.txt       "%MODEL_DIR%\" >nul
echo Bundled model installed to %MODEL_DIR%
popd
BUNDLE_EOF
    else
        echo "WARN: --with-model but model not found at ${MODEL_SRC}; skipping"
    fi
fi

# Convert shell-script line endings on .bat files to CRLF (Windows prefers).
if command -v unix2dos >/dev/null 2>&1; then
    unix2dos -q "${STAGE}/scripts/"*.bat
else
    # fallback sed-based conversion
    for f in "${STAGE}/scripts/"*.bat; do
        sed -i 's/$/\r/' "$f"
    done
fi

# Build zip.
OUT_DIR="${PROJECT_ROOT}/dist"
mkdir -p "${OUT_DIR}"
ZIP="${OUT_DIR}/${PKG_NAME}.zip"
rm -f "${ZIP}"
(cd "${STAGE_ROOT}" && zip -qr "${ZIP}" "${PKG_NAME}")

size=$(du -h "${ZIP}" | cut -f1)
echo ""
echo "  ✓ ${ZIP}  (${size})"
echo ""
echo "Target Windows usage:"
echo "  1. 解压 ${PKG_NAME}.zip"
echo "  2. cd ${PKG_NAME}"
if [[ $WITH_MODEL -eq 1 ]]; then
echo "  3. scripts\\install-bundled-model.bat   (若无网)"
fi
echo "  $([ $WITH_MODEL -eq 1 ] && echo 4 || echo 3). scripts\\setup.bat                   (装 venv + pip deps + 模型)"
echo "  $([ $WITH_MODEL -eq 1 ] && echo 5 || echo 4). scripts\\run-as-admin.bat            (启动)"
