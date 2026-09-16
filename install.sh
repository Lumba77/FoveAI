#!/usr/bin/env bash
set -e

FOVEAI_DIR="$(pwd)"
echo "🚀 Knitting together FoveAI..."

# 1. Symlink global command
echo "🔗 Setting up global 'foveai' command..."
sudo ln -sf "$FOVEAI_DIR/foveai.sh" /usr/local/bin/foveai

# 2. Systemd Service Setup
echo "⚙️ Setting up FoveAI systemd service..."
sudo cp "$FOVEAI_DIR/foveai.service" /etc/systemd/system/
sudo systemctl daemon-reload
# Don't enable it automatically unless user wants it, but make it available.
# sudo systemctl enable foveai.service

# 3. Desktop Application Shortcut
echo "🖥️ Creating Desktop Launcher..."
mkdir -p ~/.local/share/applications
cat << DESKTOP > ~/.local/share/applications/FoveAI.desktop
[Desktop Entry]
Name=FoveAI
Comment=Start the FoveAI Matrix and Services
Exec=$FOVEAI_DIR/foveai.sh --start
Icon=terminal
Terminal=false
Type=Application
Categories=Development;AI;
Actions=Stop;Status;Multigate;Vessel;

[Desktop Action Stop]
Name=Stop FoveAI
Exec=$FOVEAI_DIR/foveai.sh --stop

[Desktop Action Status]
Name=Check Status
Exec=gnome-terminal -- $FOVEAI_DIR/foveai.sh --status

[Desktop Action Multigate]
Name=Open Multigate
Exec=xdg-open http://localhost:5177

[Desktop Action Vessel]
Name=Open XR Vessel
Exec=xdg-open http://localhost:5176
DESKTOP
update-desktop-database ~/.local/share/applications || true

echo "✅ FoveAI Installation Complete!"
echo "   - Run 'foveai' from anywhere in the terminal."
echo "   - Launch 'FoveAI' from your applications menu."
echo "   - Control it via 'sudo systemctl start/stop foveai' (optional)."
