#!/usr/bin/env bash
# pocketcli installer for Arch / CachyOS / EndeavourOS / Manjaro
set -e

echo ""
echo "  pocketcli installer"
echo "  ─────────────────────────────"
echo ""

# Detect AUR helper
if command -v paru &>/dev/null; then
    AUR="paru"
elif command -v yay &>/dev/null; then
    AUR="yay"
else
    AUR="sudo pacman"
fi

echo "==> Installing dependencies with $AUR..."
$AUR -S --needed mpv python-httpx python-rich python-click

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
