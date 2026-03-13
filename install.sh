#!/bin/bash
# Install/update the per-app scaling system
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing per-app scaling system..."

# Install scripts
mkdir -p ~/.local/bin
for script in scaled-launch patch-desktop-scaling generate-wrappers app-scaling app-scaling-monitor-handler; do
    cp "$SCRIPT_DIR/scripts/$script" ~/.local/bin/
    chmod +x ~/.local/bin/$script
done

# Install config (don't overwrite if it exists, unless --force)
mkdir -p ~/.config/app-scaling
if [[ -f ~/.config/app-scaling/scales.conf && "$*" != *"--force"* ]]; then
    echo "Config already exists, skipping (use --force to overwrite)"
    # Auto-migrate old format if needed
    if ! grep -q '^\[' ~/.config/app-scaling/scales.conf; then
        echo "Detected old config format, migrating..."
        app-scaling migrate
    fi
else
    cp "$SCRIPT_DIR/config/scales.conf" ~/.config/app-scaling/
fi

# Add ~/.local/bin/scaled to PATH in .bashrc if not already there
BASHRC="$HOME/.bashrc"
PATH_LINE='export PATH="$HOME/.local/bin/scaled:$PATH"'
if ! grep -qF '.local/bin/scaled' "$BASHRC" 2>/dev/null; then
    echo "" >> "$BASHRC"
    echo "# Per-app scaling wrappers" >> "$BASHRC"
    echo "$PATH_LINE" >> "$BASHRC"
    echo "Added ~/.local/bin/scaled to PATH in .bashrc"
    # Also export for the current session
    export PATH="$HOME/.local/bin/scaled:$PATH"
else
    echo "PATH already configured in .bashrc"
fi

# Run setup (generate wrappers + patch desktop files)
echo ""
app-scaling setup

# Install udev rule for monitor auto-detection
echo ""
echo "=== Monitor Auto-Detection ==="
HANDLER_PATH="$HOME/.local/bin/app-scaling-monitor-handler"
UDEV_RULE="/etc/udev/rules.d/99-app-scaling-monitor.rules"

if [[ -f "$UDEV_RULE" ]]; then
    echo "udev rule already installed at $UDEV_RULE"
else
    echo "Install udev rule for automatic monitor hotplug detection?"
    echo "This requires sudo and will create: $UDEV_RULE"
    read -rp "Install? [y/N] " answer
    if [[ "$answer" =~ ^[Yy] ]]; then
        # Generate the rule with the correct handler path
        RULE_CONTENT="SUBSYSTEM==\"drm\", ACTION==\"change\", RUN+=\"${HANDLER_PATH}\""
        echo "$RULE_CONTENT" | sudo tee "$UDEV_RULE" > /dev/null
        sudo udevadm control --reload-rules
        echo "udev rule installed and rules reloaded."
    else
        echo "Skipped. To install manually later:"
        echo "  echo 'SUBSYSTEM==\"drm\", ACTION==\"change\", RUN+=\"${HANDLER_PATH}\"' | sudo tee $UDEV_RULE"
        echo "  sudo udevadm control --reload-rules"
    fi
fi

echo ""
echo "Done! Per-app scaling is now active."
echo ""
echo "Usage:"
echo "  app-scaling status              — see what's configured"
echo "  app-scaling test APP            — preview scaling for an app"
echo "  app-scaling setup               — regenerate wrappers + desktop patches"
echo "  app-scaling teardown            — remove all scaling hooks"
echo "  app-scaling global PCT          — change GNOME fractional scaling"
echo "    --relative                    — adjust per-app factors to compensate"
echo "    --no-save                     — don't save adjusted factors to config"
echo ""
echo "Config: ~/.config/app-scaling/scales.conf"
