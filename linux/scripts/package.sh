#!/usr/bin/env bash
#
# Create a distributable tarball of voice-ibus.
#
# Default output: voice-ibus-<version>.tar.gz  (~50 KB, source only)
# With --with-model: voice-ibus-<version>-with-model.tar.gz (~230 MB)
#
# Target machine usage:
#   tar xf voice-ibus-*.tar.gz
#   cd voice-ibus-*
#   ./bootstrap.sh       # installs system deps + venv + model + ibus component
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
            echo "  --with-model   Include the downloaded Paraformer model (~230 MB)"
            exit 0
            ;;
        *) echo "Unknown arg: $arg"; exit 2 ;;
    esac
done

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGE_DIR}"' EXIT

suffix=""
[[ $WITH_MODEL -eq 1 ]] && suffix="-with-model"
PKG_NAME="voice-ibus-${VERSION}${suffix}"
STAGE_PKG="${STAGE_DIR}/${PKG_NAME}"
mkdir -p "${STAGE_PKG}"

echo "Staging files into ${STAGE_PKG}..."

# Source tree — no .venv, no caches, no git.
rsync -a \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='.git' \
    --exclude='.mypy_cache' \
    --exclude='*.egg-info' \
    --exclude='dist' \
    --exclude='build' \
    --include='src/***' \
    --include='tests/***' \
    --include='resources/***' \
    --include='docs/***' \
    --include='scripts/***' \
    --include='pyproject.toml' \
    --include='README.md' \
    --include='HANDOFF-WINDOWS.md' \
    --include='*/' \
    --exclude='*' \
    "${PROJECT_ROOT}/" "${STAGE_PKG}/"

# Bundled model (optional)
if [[ $WITH_MODEL -eq 1 ]]; then
    MODEL_SRC="${HOME}/.local/share/ibus-voice/models/paraformer-zh"
    if [[ -d "${MODEL_SRC}" ]]; then
        echo "Including model from ${MODEL_SRC}..."
        mkdir -p "${STAGE_PKG}/bundled-model"
        # Only the 3 files we actually need at runtime.
        cp "${MODEL_SRC}/model.int8.onnx" "${STAGE_PKG}/bundled-model/"
        cp "${MODEL_SRC}/tokens.txt" "${STAGE_PKG}/bundled-model/"
    else
        echo "WARN: --with-model requested but model not found at ${MODEL_SRC}; skipping"
        WITH_MODEL=0
    fi
fi

# Create bootstrap script at top of package.
cat > "${STAGE_PKG}/bootstrap.sh" <<'BOOTSTRAP_EOF'
#!/usr/bin/env bash
#
# One-shot install for voice-ibus on a fresh Ubuntu 22.04/24.04 machine.
# Run: ./bootstrap.sh
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

echo "=== voice-ibus bootstrap ==="
echo ""

# ---- 1. System package deps ----
SYS_DEPS=(
    python3-gi
    python3-ibus-1.0
    gir1.2-ibus-1.0
    gir1.2-glib-2.0
    pipewire-bin       # provides pw-record
    alsa-utils         # fallback
    ibus
    libnotify-bin      # for notify-send (optional but nice)
)
need_install=()
for pkg in "${SYS_DEPS[@]}"; do
    dpkg -s "$pkg" &>/dev/null || need_install+=("$pkg")
done
if (( ${#need_install[@]} > 0 )); then
    echo "Installing system deps: ${need_install[*]}"
    sudo apt-get update
    sudo apt-get install -y "${need_install[@]}"
else
    echo "System deps: OK"
fi

# ---- 2. uv (fast Python package manager) ----
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
fi
echo "uv: $(command -v uv)"

# ---- 3. venv + editable install ----
if [[ ! -d .venv ]]; then
    echo "Creating .venv (with system site-packages for PyGObject/IBus bindings)..."
    uv venv --system-site-packages
fi
uv pip install -e . --quiet
uv pip install numpy sherpa-onnx --quiet   # explicit in case pyproject parsed oddly
echo ".venv: $(.venv/bin/python --version)"

# ---- 4. Model ----
MODEL_DIR="${HOME}/.local/share/ibus-voice/models/paraformer-zh"
if [[ -f "${PROJECT_ROOT}/bundled-model/model.int8.onnx" ]]; then
    echo "Installing bundled model..."
    mkdir -p "${MODEL_DIR}"
    cp "${PROJECT_ROOT}/bundled-model/model.int8.onnx" "${MODEL_DIR}/"
    cp "${PROJECT_ROOT}/bundled-model/tokens.txt" "${MODEL_DIR}/"
elif [[ ! -f "${MODEL_DIR}/model.int8.onnx" ]]; then
    echo "Downloading Paraformer model (one-time)..."
    .venv/bin/python scripts/download-model.py --small
else
    echo "Model already present at ${MODEL_DIR}"
fi

# ---- 5. Seed default config ----
USER_CFG="${HOME}/.config/ibus-voice/config.toml"
if [[ ! -f "${USER_CFG}" ]]; then
    mkdir -p "$(dirname "${USER_CFG}")"
    cp resources/default-config.toml "${USER_CFG}"
    echo "Seeded default config: ${USER_CFG}"
fi

# ---- 6. Register IBus component (needs sudo) ----
echo "Registering IBus component (requires sudo — one-time)..."
./scripts/install.sh

echo ""
echo "=== Install complete ==="
echo ""
echo "Next steps:"
echo "  1. GNOME Settings → Keyboard → Input Sources → '+' → Chinese → Voice"
echo "  2. Super+Space 切到 Voice"
echo "  3. 光标落到文本框 → 按住 CapsLock 说话 → 松开"
echo ""
echo "Logs: tail -f ~/.cache/ibus-voice/service.log"
BOOTSTRAP_EOF
chmod +x "${STAGE_PKG}/bootstrap.sh"

# Minimal TARGET-README for the recipient.
cat > "${STAGE_PKG}/INSTALL.md" <<'INSTALL_EOF'
# 在目标 Ubuntu 机器上安装

```bash
# 解压后进入目录
cd voice-ibus-*

# 一条命令装完（会调用 sudo 装系统包 + 注册 IBus 组件）
./bootstrap.sh
```

**系统要求**：
- Ubuntu 22.04 或 24.04
- GNOME + Wayland（X11 也能用但未测）
- 可用麦克风（USB 头戴 or 3.5mm 插到正确接口）
- 网络（除非是 `-with-model` 包，否则会下载 ~80 MB 模型）
- sudo 权限（装系统包 + 把 XML 放到 /usr/share/ibus/component/）

**使用**：
1. GNOME Settings → Keyboard → Input Sources → `+` → 选 Chinese → 找 "Voice"
2. Super+Space 切到 Voice 输入法
3. 光标落到任何文本框，按住 CapsLock 说话，松开 → 文字上屏

**卸载**：
```bash
./scripts/uninstall.sh
rm -rf ~/.local/share/ibus-voice ~/.config/ibus-voice ~/.cache/ibus-voice
```

**排错**：见项目内 README.md。
INSTALL_EOF

# Build tarball.
OUT_DIR="${PROJECT_ROOT}/dist"
mkdir -p "${OUT_DIR}"
TARBALL="${OUT_DIR}/${PKG_NAME}.tar.gz"
echo ""
echo "Creating ${TARBALL}..."
tar -C "${STAGE_DIR}" -czf "${TARBALL}" "${PKG_NAME}"

size=$(du -h "${TARBALL}" | cut -f1)
echo ""
echo "  ✓ ${TARBALL}  (${size})"
echo ""
echo "Copy to target machine, then:"
echo "  tar xf ${PKG_NAME}.tar.gz"
echo "  cd ${PKG_NAME}"
echo "  ./bootstrap.sh"
