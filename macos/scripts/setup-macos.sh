#!/bin/bash
# macOS setup for voice-input
set -e

echo "1. Checking Python..."
python3 --version

echo "2. Creating venv..."
python3 -m venv .venv
source .venv/bin/activate

echo "3. Installing dependencies..."
pip install -e ".[macos]"

APP_SUPPORT="$HOME/Library/Application Support/voice-input"

echo "4. Downloading Paraformer model..."
python scripts/download-model.py --dest "$APP_SUPPORT/models/paraformer-zh" --small

echo "5. Copying default config..."
mkdir -p "$APP_SUPPORT"
if [ ! -f "$APP_SUPPORT/config.toml" ]; then
    cp resources/default-config-macos.toml "$APP_SUPPORT/config.toml"
    echo "  Config seeded at $APP_SUPPORT/config.toml"
else
    echo "  Config already exists, skipping."
fi

echo ""
echo "Done! Run with:"
echo "  source .venv/bin/activate"
echo "  voice-input-macos"
echo ""
echo "IMPORTANT: Grant Accessibility permission when prompted,"
echo "or go to System Settings > Privacy & Security > Accessibility"
