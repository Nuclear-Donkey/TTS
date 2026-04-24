#!/usr/bin/env bash
#
# Install voice-ibus.
#
# Ubuntu/Debian IBus (1.5.29) only scans component XMLs from the compile-time
# path /usr/share/ibus/component — ~/.local/share/ibus/component/ is NOT
# discovered. So we need ONE sudo step to drop the XML there. All other state
# (models, config, logs) stays user-level.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${PROJECT_ROOT}/.venv/bin/python"
SYSTEM_COMPONENT_DIR="/usr/share/ibus/component"
SYSTEM_COMPONENT_FILE="${SYSTEM_COMPONENT_DIR}/voice.xml"
TEMPLATE="${PROJECT_ROOT}/resources/voice.xml"
TMP_RENDERED="$(mktemp --suffix=.xml)"
trap 'rm -f "${TMP_RENDERED}"' EXIT

if [[ ! -x "${VENV_PY}" ]]; then
    echo "ERROR: venv not found at ${VENV_PY}" >&2
    echo "Run: cd ${PROJECT_ROOT} && uv venv --system-site-packages && uv pip install -e ." >&2
    exit 1
fi

# Verify editable install — daemon exec won't set PYTHONPATH for us.
if ! "${VENV_PY}" -c "import voice_ibus" 2>/dev/null; then
    echo "Installing package in editable mode..."
    (cd "${PROJECT_ROOT}" && uv pip install -e . >/dev/null)
fi

if [[ ! -f "${TEMPLATE}" ]]; then
    echo "ERROR: template not found: ${TEMPLATE}" >&2
    exit 1
fi

# Render the component XML with the correct venv path.
# Package must be installed into the venv (`uv pip install -e .`) so we don't
# need PYTHONPATH here — the daemon's own PATH can be weirdly pruned and may
# not contain /usr/bin/env, so keep the exec line absolute and env-free.
EXEC_CMD="${VENV_PY} -m voice_ibus --ibus"
sed "s|@EXEC_PATH@|${EXEC_CMD}|g" "${TEMPLATE}" > "${TMP_RENDERED}"

echo "Will install:"
echo "  ${TMP_RENDERED}"
echo "  → ${SYSTEM_COMPONENT_FILE}"
echo "  exec: ${EXEC_CMD}"
echo ""
echo "This requires sudo (one-time) because IBus only scans system paths."
echo ""

sudo install -m 0644 "${TMP_RENDERED}" "${SYSTEM_COMPONENT_FILE}"
echo "Installed."

# Clean up any old user-level install from previous script version.
rm -f "${HOME}/.local/share/ibus/component/voice.xml"

# Seed default user config if none exists.
USER_CONFIG_DIR="${HOME}/.config/ibus-voice"
USER_CONFIG="${USER_CONFIG_DIR}/config.toml"
if [[ ! -f "${USER_CONFIG}" ]]; then
    mkdir -p "${USER_CONFIG_DIR}"
    cp "${PROJECT_ROOT}/resources/default-config.toml" "${USER_CONFIG}"
    echo "Seeded default config at ${USER_CONFIG}"
fi

# Ensure model present (non-fatal if offline).
MODEL_FILE="${HOME}/.local/share/ibus-voice/models/paraformer-zh/model.int8.onnx"
if [[ ! -f "${MODEL_FILE}" ]]; then
    echo ""
    echo "Downloading STT model (one-time)..."
    "${VENV_PY}" "${PROJECT_ROOT}/scripts/download-model.py" --small || {
        echo "WARN: model download failed. Run manually later:"
        echo "  ${VENV_PY} scripts/download-model.py --small"
    }
fi

echo ""
echo "Restarting IBus daemon..."
ibus exit 2>/dev/null || true
sleep 1
ibus-daemon -drx &
sleep 3

if ibus list-engine --name-only 2>/dev/null | grep -qx voice; then
    echo "  ✓ 'voice' engine registered with IBus"
else
    echo "  ✗ 'voice' not seen by ibus. Re-run or check:"
    echo "    journalctl --user -n 50 | grep -i ibus"
    exit 1
fi

echo ""
echo "Next steps:"
echo "  1. Open GNOME Settings → Keyboard → Input Sources"
echo "  2. Click '+' and pick '🎤 Voice' (under Chinese 中文)"
echo "  3. Switch input sources with Super+Space until you see the Voice icon"
echo "  4. Focus any text field, press and hold CapsLock, speak, release"
echo ""
echo "Logs: ~/.cache/ibus-voice/service.log"
