# Remote Chrome Desktop Installer

Installs and configures **Chrome Remote Desktop** as a system service on virtually any Linux machine.

## Quick Start

```bash
# Interactive (prompts for OAuth code)
./install.sh

# Non-interactive
./install.sh --code="4/0AXxYourOAuthCodeHere"
```

## How It Works

1. Detects your Linux distribution and architecture
2. Downloads the official Chrome Remote Desktop package from Google
3. Installs it (via apt on Debian/Ubuntu, or manual extraction on RPM-based distros)
4. Configures the host with your Google account
5. Creates a systemd service (`crd-host.service`) that starts on boot
6. No port forwarding needed — works through Google's relay

## Getting an OAuth Code

1. Open a browser on the target machine
2. Go to [remotedesktop.google.com](https://remotedesktop.google.com)
3. Click **"Set up remote access"**
4. Copy the authorization code from the URL

## Supported Distros

| Distro Family | Examples |
|---|---|
| Debian-based | Debian, Ubuntu, Mint, Pop!_OS |
| RPM-based | Fedora, RHEL, CentOS, Rocky, Alma, Nobara |
| Arch-based | Arch, Manjaro, EndeavourOS |
| SUSE-based | openSUSE, SUSE |

## After Installation

From any browser (including VR headsets like Quest 3):

1. Go to [remotedesktop.google.com/access](https://remotedesktop.google.com/access)
2. Sign in with the same Google account used during setup
3. Click your machine name
4. Enter the PIN you set

## Service Commands

```bash
sudo systemctl status crd-host    # Check status
sudo systemctl restart crd-host   # Restart
sudo systemctl stop crd-host      # Stop
sudo systemctl disable crd-host   # Disable autostart
```

## Requirements

- Root or sudo access
- Internet connection
- `wget` (auto-installed if missing)
- A display (for the desktop session)

## Files Installed

| Path | Purpose |
|---|---|
| `/opt/google/chrome-remote-desktop/` | CRD binaries |
| `~/.config/chrome-remote-desktop/host.json` | Host configuration |
| `/etc/systemd/system/crd-host.service` | Systemd service |
