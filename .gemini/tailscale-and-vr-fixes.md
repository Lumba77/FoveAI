# Lumax Nexus: Tailscale & VR Certification Plan

## Objective
Finalize the network bridge by registering the Docker Tailscale server (`lumax_net`) and the host PC, then deploy the spatial UI and animation fixes to the Quest using its stable Tailscale IP (`100.64.150.192`).

## Implementation Steps

### 1. Tailscale Docker Registration
* **Start Container:** Bring up the `lumax_net` container using `docker-compose up -d lumax_net`.
* **Fetch Login URL:** Retrieve the Tailscale authentication URL from the container logs (`docker logs lumax_net`).
* **User Action:** The user will click the URL to authorize the Docker network onto the Tailnet (`TK9kmqGC2N11CNTRL`).

### 2. ADB Persistent Bridge
* **Restart ADB:** Ensure the host PC can ping the Quest's Tailscale IP.
* **Connect:** Run `adb connect 100.64.150.192:5555`.

### 3. Master Certification Push (VR Fixes)
* **Wipe Cache:** Clear `/sdcard/Projects/Lumax-Vulkan/.godot/` via the Tailscale ADB connection.
* **Deploy Code:** Push `SkeletonKey.gd`, `WebUI.gd`, `TactileInput.gd`, `avatar_controller.gd`, and `Lumax_Display.tscn`.
* **Restart App:** Force stop the Godot editor to trigger a fresh import of the 4px UI frame and T-Pose fixes.

### 4. Swarm Router Architecture (Task 5)
* Begin drafting the "Integrative Protocol" in `compagent.py` to route requests between a fast "Conductor" model and specialized nodes (Vision/Creativity).
