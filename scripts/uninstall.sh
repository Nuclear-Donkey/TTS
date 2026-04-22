#!/usr/bin/env bash
set -euo pipefail

echo "Removing IBus component (requires sudo)..."
sudo rm -f /usr/share/ibus/component/voice.xml
rm -f "${HOME}/.local/share/ibus/component/voice.xml" 2>/dev/null || true

echo "Restarting IBus..."
ibus exit 2>/dev/null || true
sleep 1
ibus-daemon -drx &
sleep 2

echo ""
echo "Removed. User data kept (remove manually if you want a clean slate):"
echo "  ~/.local/share/ibus-voice/   # downloaded model (~80MB)"
echo "  ~/.config/ibus-voice/        # config"
echo "  ~/.cache/ibus-voice/         # logs"
