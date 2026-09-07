# The Wonder Pedal - Paradiddle Proof of Concept

This directory contains the Proof of Concept (PoC) for the Wonder Pedal platform, specifically targeting integration with the **Paradiddle VR Drum App**.

## Architecture Overview

To achieve zero-latency integration without modifying Paradiddle's code, we utilize a **Bridge Architecture**:

1. **The Quest Sensor (XR App):** A lightweight Quest application (built in WebXR or Unity) uses the Meta Movement SDK (Inside-Out Body Tracking) to track the spatial velocity of the left and right knees. When a "hit" velocity threshold is reached, it fires a lightweight UDP/OSC packet.
2. **The Wonder Bridge:** The Python script (`paradiddle_bridge.py`) runs locally and listens for these incoming UDP/OSC hits from the Quest.
3. **The Injector:** The Bridge instantly converts the incoming packets into standard **Virtual MIDI Notes** (Kick = 36, Hi-Hat = 44) or **Paradiddle OSC Commands**. Paradiddle natively listens to these, perfectly tricking the game into registering a physical pedal hit.

## Next Steps for PoC
- Test the bridge locally.
- Build the Quest XR Sensor (WebXR) to beam tracking data to the bridge.
