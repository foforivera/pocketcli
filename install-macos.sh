#!/usr/bin/env bash
# pocketcli installer for macOS
set -e

echo ""
echo "  pocketcli installer for macOS"
echo "  ─────────────────────────────"
echo ""

# Check Homebrew
if ! command -v brew &>/dev/null; then
    echo "==> Homebrew not found. Install it from https://brew.sh and re-run."
    exit 1
fi

echo "==> Installing dependencies..."
brew install mpv

# Python deps via pip
if command -v pip3 &>/dev/null; then
    pip3 install httpx rich click --break-system-packages 2>/dev/null || \
    pip3 install httpx rich click
elif command -v pip &>/dev/null; then
    pip install httpx rich click
else
    echo "==> pip not found. Install Python from https://python.org"
    exit 1
fi

# Install script
INSTALL_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"
cp pocketcli.py "$INSTALL_DIR/pocketcli"
chmod +x "$INSTALL_DIR/pocketcli"
echo "==> Installed to $INSTALL_DIR/pocketcli"

# Fish shell config
FISH_CONFIG="$HOME/.config/fish/config.fish"
if [ -f "$FISH_CONFIG" ]; then
    if ! grep -q "\.local/bin" "$FISH_CONFIG" 2>/dev/null; then
        echo 'fish_add_path $HOME/.local/bin' >> "$FISH_CONFIG"
        echo "==> Added ~/.local/bin to fish PATH"
    fi
    if ! grep -q "pocketcli-update" "$FISH_CONFIG" 2>/dev/null; then
        echo 'alias pocketcli-update="mv ~/Downloads/pocketcli.py ~/.local/bin/pocketcli && chmod +x ~/.local/bin/pocketcli && echo pocketcli updated"' >> "$FISH_CONFIG"
        echo "==> Added pocketcli-update alias to fish"
    fi
fi

# Bash/zsh config
for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$RC" ]; then
        if ! grep -q "\.local/bin" "$RC" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
            echo "==> Added ~/.local/bin to PATH in $RC"
        fi
        if ! grep -q "pocketcli-update" "$RC" 2>/dev/null; then
            echo 'alias pocketcli-update="mv ~/Downloads/pocketcli.py ~/.local/bin/pocketcli && chmod +x ~/.local/bin/pocketcli && echo pocketcli updated"' >> "$RC"
        fi
    fi
done

echo ""
echo "  Done! Open a new terminal and run:"
echo ""
echo "    pocketcli"
echo ""
