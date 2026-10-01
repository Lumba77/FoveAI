# Audio Variator EQ & Studio Effects Suite

A zero-latency, glitch-free system-wide audio shaping and pitch modulation suite for Linux (PipeWire / Linux Mint Cinnamon).

Integrated directly into the Cinnamon desktop taskbar volume popup and available via standalone GUI and CLI.

---

## Features

### 1. 🎛 Embedded Taskbar Audio Popup (`sound@cinnamon.org`)
Left-click the speaker icon in your taskbar to access:
* **3-Band Harmonic Equalizer**:
  * **BASS** (`Sub & Kick`): Low-frequency shelf at 100 Hz (`−12 dB` to `+12 dB`).
  * **MID** (`Vocals`): Midrange peak at 1 kHz (`−12 dB` to `+12 dB`).
  * **TREBLE** (`Air & Detail`): High-frequency shelf at 8 kHz (`−12 dB` to `+12 dB`).
* **Dual Frequency Balancers (`Freq. Bal.`)**:
  * **Low/Mid Balancer**: Emphasizes either Sub/Kick or Mid vocal clarity (`FLAT`, `LOW`, `MID`).
  * **Mid/High Balancer**: Emphasizes either Mid warmth or High sparkle/air (`FLAT`, `MID`, `HIGH`).
* **🎵 Pitch & Tape Glide**:
  * **PITCH** (`Tone / Key`): Real-time musical pitch shift from `−12` to `+12` semitones while **keeping playback speed 100% constant**. Uses Rubber Band R3 phase-vocoder math with formant preservation.
  * **WARP** (`Tape Glide`): Micro-pitch cents glide (`−100` to `+100` ct) for analog tape drift and turntable vari-speed inertia.
  * **0 RESET**: Snaps pitch and warp back to standard neutral.
* **Studio Effects Sub-menu (All Labeled Left-Right Screws)**:
  * **COMPRESSOR** (`Dynamic Lev.`): Levels volume peaks and lifts quiet details (`0% – 100%`).
  * **LOUDNESS** (`Contour Boost`): Equal-loudness bass/treble boost for rich low-volume listening (`0% – 100%`).
  * **CHORUS** (`Stereo Shimmer`): Multi-voice doubling and stereo shimmer (`0% – 100%`).
  * **REVERB** (`Acoustic Space`): Natural acoustic room depth and ambience (`0% – 100%`).
  * **FREQ MOD** (`Band Sweep`): Wide resonant frequency focus sweep (`0% – 100%`).
  * **Reset All EQ & Effects**: One-click restore to flat defaults.

*Note: All screws support mouse wheel scrolling — hover over any screw and scroll to adjust!*

---

## Files in this Directory

| File | Description |
|---|---|
| `set-eq` | Python CLI and live parameter controller using PipeWire SPA properties |
| `pipewire-eq-gui` | Standalone GTK3 3-Band Equalizer window |
| `sink-eq.conf` | Native PipeWire filter-chain configuration (Biquads + Rubber Band R3) |
| `pipewire-eq.desktop` | Application menu desktop launcher |
| `cinnamon-applet/` | Complete customized Cinnamon sound applet with embedded screws and dual balancers |
| `install.sh` | One-step installer script to restore or install on any user account |

---

## Installation & Deployment

To install or restore on this machine or a new system:

```bash
# 1. Install prerequisites (Rubber Band LADSPA engine)
sudo apt install -y rubberband-ladspa

# 2. Run installer
./install.sh
```

---

## CLI Usage

Adjust parameters live from terminal, scripts, or shortcuts:

```bash
# Check current status
set-eq --status

# Output full state as JSON
set-eq --json

# Adjust EQ bands
set-eq --bass -3.0
set-eq --mid +1.5
set-eq --treble +2.0

# Pitch shift by +2 semitones (keep speed)
set-eq --pitch +2

# Cycle low frequency balancer
set-eq --toggle-bal-low

# Adjust studio effects
set-eq --compressor 40
set-eq --loudness 50

# Reset everything to flat defaults
set-eq --reset
```
