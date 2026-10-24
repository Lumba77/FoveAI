
- ✅ **Holonic Network Topology** (Sky Net, Sovereign Core, Worker Swarms, Stardust Gnists)
- ✅ **Native XRLation & Principiation** (Source code and conversation compression via XRL; extracting the core *principia* / principles and invariants rather than crude skeletons, with `xrl://` on-demand active recall. TokenSlayer and third-party tools like SigMap are retired in favor of native XRLation.)

## Prerequisites & Toolchain

FoveAI spans three toolchains. Install each only for the components you intend to run.

### 1. Python runtime (XRLF, API, memory, AI inference)

- **Python 3.12** (3.14 is too new — many native wheels are missing)
- **UV** package manager: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **C++ build tools** (for `llama-cpp-python` compilation): `gcc`, `g++`, `make`
- **espeak-ng** (for TTS phonemizer): system package `espeak-ng`

```bash
uv venv .venv --python 3.12
uv pip install -r requirements.txt
```

Optional extras (creative stack, vector DB, cloud APIs): `uv pip install -r requirements-optional.txt`

Dev/test: `uv pip install -r requirements-dev.txt`

### 2. Node.js proxy & dashboard (foveated-memory)

- **Node.js >= 18** (tested on 22.x)
- **npm** (bundled with Node.js)

```bash
cd foveated-memory
npm install
```

### 3. Unity & Android (XR vessel APK builds)

- **Unity 6000.4.9 (Unity 6)** — license file: `Unity_v6000.4.9f1.alf`
- **Android SDK** with:
  - `compileSdk` 34 (Android 14)
  - `minSdk` 29 for Quest vessels (Quest 2/3, Android 10+)
  - `minSdk` 26 for Phone Wrapper (Android 8+)
- **Android NDK** (selected by Unity during APK build)
- **Gradle** (bundled via `gradlew` wrapper in each Android project)
- **JDK 17** (required by Android Gradle Plugin 8.x)

Build targets:
- `Forge/Quest_Vessel/` — Meta Quest XR app (`se.lumax.vessel`)
- `Frontend/Phone_Wrapper/` — Android phone companion

### 4. System-level (Linux desktop)

- **NVIDIA driver** (for GPU inference — runtime currently CPU-only until CUDA-enabled llama.cpp is built)
- **GTK3 + AppIndicator3** (for system tray: `FoveAI_Taskbar_Linux.py`)
- **espeak-ng** (TTS fallback)
- **OpenSSL** (HTTPS tunneling via cloudflared, optional)

## Getting Started

To ignite the Lumax fleet, ensure your local Python `.venv` is configured, and execute the master orchestrator from your terminal:

```powershell
.\Start_Concordia.ps1
```

For philosophical and technical insights into how the system interprets the user's intent, read [introduction.md](introduction.md), [XRLF Manual and Implementation.md](XRLF%20Manual%20and%20Implementation.md), and [ARCHITECTURE.md](ARCHITECTURE.md).

## Development Log

See [Context.md](Context.md) for the latest session developments, environment changes, and build notes.

### Recent highlights (2026-09-11)
- **XR Thumbstick Locomotion**: Left stick moves, right stick snap-turns (new Input System, OpenXR bindings)
- **Sociable Alice**: Follow mode by default, stands in front of player, Clingy mood, looks at you 70% of time
- **Passthrough fix**: Camera clear flags + Mixed Reality capability group in AndroidManifest
- **Linux environment rebuilt** after reinstall: Python 3.12 venv, Unity 6000.4.9f1, xrdp, firewall configured
