#!/usr/bin/env bash
#
# install.sh — Installs the Audio Variator EQ & Effects Suite into the active user session.
#
# Suite contents:
#   set-eq           — output-lane controller (EQ, pitch/warp, comp, space, mod, tilt; scenes + unit presets)
#   set-mic-fx       — input-lane controller (mic capture FX chain)
#   pipewire-eq-gui  — standalone zenity GUI (optional)
#   sink-eq.conf     — PipeWire filter-chain: output DSP graph
#   mic-fx.conf      — PipeWire filter-chain: input DSP graph
#   impulses/*.wav   — convolution reverb IRs
#   fovefx.c         — custom LADSPA plugins (width mixer etc.), built to ~/.ladspa
#   cinnamon-applet/ — patched Cinnamon sound applet with the two-lane mixer UI
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing Audio Variator EQ & Effects Suite ==="

# 1. CLI & GUI tools
mkdir -p "$HOME/.local/bin"
cp -p "$SCRIPT_DIR/set-eq" "$SCRIPT_DIR/set-mic-fx" "$SCRIPT_DIR/pipewire-eq-gui" "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/set-eq" "$HOME/.local/bin/set-mic-fx" "$HOME/.local/bin/pipewire-eq-gui"
echo "  ✓ Installed set-eq, set-mic-fx, pipewire-eq-gui to ~/.local/bin"

# 2. Desktop launcher
mkdir -p "$HOME/.local/share/applications"
cp -p "$SCRIPT_DIR/pipewire-eq.desktop" "$HOME/.local/share/applications/"
echo "  ✓ Installed desktop launcher"

# 3. PipeWire filter-chain configs + impulses
mkdir -p "$HOME/.config/pipewire/pipewire.conf.d" "$HOME/.config/pipewire/impulses"
cp -p "$SCRIPT_DIR/sink-eq.conf" "$SCRIPT_DIR/mic-fx.conf" "$HOME/.config/pipewire/pipewire.conf.d/"
sed -i "s|/home/lumba/.config/pipewire/impulses|$HOME/.config/pipewire/impulses|g" \
    "$HOME/.config/pipewire/pipewire.conf.d/sink-eq.conf" \
    "$HOME/.config/pipewire/pipewire.conf.d/mic-fx.conf"
cp -p "$SCRIPT_DIR/impulses/"*.wav "$HOME/.config/pipewire/impulses/" 2>/dev/null || true
echo "  ✓ Installed filter-chain configs and impulses"

# 4. Custom LADSPA plugins (fovefx: width/mixer helpers)
if command -v gcc >/dev/null 2>&1; then
    mkdir -p "$HOME/.ladspa"
    # Build with math library explicitly linked as needed for tanhf
    gcc -shared -fPIC -O2 -o "$HOME/.ladspa/fovefx.so" "$SCRIPT_DIR/fovefx.c" -Wl,--no-as-needed -lm
    
    # Also copy to the system LADSPA dir (requires sudo) to bypass PipeWire sandbox issues
    if [ -d "/usr/lib/ladspa" ]; then
        echo "  [Sudo] Copying fovefx.so to system /usr/lib/ladspa/ (may prompt for password)..."
        sudo cp "$HOME/.ladspa/fovefx.so" "/usr/lib/ladspa/fovefx.so" || echo "  ! Failed to copy to /usr/lib/ladspa/ - PipeWire might fail to load it."
    fi
    
    # Back up to the older audio_fx folder for legacy reference
    if [ -d "$HOME/FoveAI/tools/audio_fx" ]; then
        cp "$HOME/.ladspa/fovefx.so" "$HOME/FoveAI/tools/audio_fx/fovefx.so"
    fi
    echo "  ✓ Built fovefx.so and deployed"
else
    echo "  ! gcc not found — skipping fovefx.so build (pitch/width features need it)"
fi

if [ ! -e "$HOME/.ladspa/am_pitchshift_1433.so" ] && [ ! -e /usr/lib/ladspa/am_pitchshift_1433.so ]; then
    echo "  ! swh-plugins (amPitchshift) not found — install it via 'sudo apt-get install swh-plugins' for pitch/warp to work"
fi

# Fix ladspa paths in the deployed config to use the system path if they were hardcoded
sed -i "s|/home/lumba/.ladspa/fovefx.so|/usr/lib/ladspa/fovefx.so|g" \
    "$HOME/.config/pipewire/pipewire.conf.d/sink-eq.conf" \
    "$HOME/.config/pipewire/pipewire.conf.d/mic-fx.conf"
sed -i "s|/home/lumba/.ladspa/am_pitchshift_1433.so|/usr/lib/ladspa/am_pitchshift_1433.so|g" \
    "$HOME/.config/pipewire/pipewire.conf.d/sink-eq.conf" \
    "$HOME/.config/pipewire/pipewire.conf.d/mic-fx.conf"


# 5. Cinnamon Sound Applet integration
mkdir -p "$HOME/.local/share/cinnamon/applets/sound@cinnamon.org"
cp -rp "$SCRIPT_DIR/cinnamon-applet/"* "$HOME/.local/share/cinnamon/applets/sound@cinnamon.org/"
echo "  ✓ Installed customized Cinnamon sound applet"

# 6. Reload services
echo "Reloading PipeWire..."
systemctl --user restart pipewire pipewire-pulse 2>/dev/null || true
sleep 1.5

if command -v pactl >/dev/null 2>&1; then
    pactl set-default-sink effect_input.eq 2>/dev/null || true
fi

echo "Reloading Cinnamon sound applet..."
if command -v cinnamon-dbus-command >/dev/null 2>&1; then
    cinnamon-dbus-command ReloadXlet sound@cinnamon.org APPLET 2>/dev/null || true
fi

echo "=== Installation complete! ==="
echo "Open the taskbar sound icon → mixer, or run 'set-eq --status' / 'set-eq --presets-json'."
