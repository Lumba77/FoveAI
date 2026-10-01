# Wonder Pedal Tracking Theory: The Dual-Measurement Architecture

This document outlines the theoretical foundation and physics calculations for the Wonder Pedal tracking system. It defines how we capture human kinetic intent (drumming) using optical inside-out tracking, while overcoming the inherent limitations of camera-based occlusion.

## 1. The Core Philosophy: Heel-Up Inflection Tracking
In standard drumming, the "Heel-Up" technique is used for powerful, fast strokes. Tracking this digitally requires moving away from static positional data (where the foot *is*) and focusing on kinetic inflection (how the foot *moves*).

### The Primary Measurement (Y-Axis Velocity)
Instead of waiting for the foot to cross a virtual floor, the system tracks the mathematical derivative of the knee's position over time (`deltaY / deltaTime`).
1. **The Inflection Point ("The Zoop"):** The system detects the exact millisecond the knee reaches the top of its arc and accelerates downwards. 
2. **Auto-Calibration:** The system records the absolute maximum downward velocity (e.g., the drummer's initial "test thump"). It dynamically sets this as the `maxVelocity` ceiling, allowing all subsequent, softer hits to scale proportionally on a MIDI gradient (0–127).

## 2. The Occlusion Fallback: The Sensory Lines (Mesh Deformation Tracking)
The primary challenge in optical tracking is occlusion (e.g., the drummer's hands crossing over the knee to play the hi-hat, blinding the cameras). To solve this, the system relies on a **Secondary Measurement Model**.

### The Virtual Sensory Lines
Rather than tracking a single point (the knee), the system generates two virtual "Sensory Lines" along the outer and inner edges of the thigh. 
* **The Resting State:** When the knee is raised (Heel-Up), the sensory lines align perfectly with the upper boundary of the leg's physical volume.
* **The Gap Detection:** When the knee drops to strike the pedal, the entire thigh shifts downwards. Even if the knee is hidden by hands, the upper thigh remains visible. The system measures the "gap" (or delta) between the original Resting State line and the new lowered thigh boundary.
* **Triggering:** If the gap widens at a sufficient speed, the system infers a downward strike and registers the hit, entirely bypassing the occluded knee.

## 3. The Interpolation Engine
To ensure perfect timing when the primary measurement (the knee) is suddenly lost, the system uses predictive interpolation.
* **Trajectory Assumption:** If the knee is accelerating downwards at 1.5 m/s, and the camera loses sight of it for 3 frames, the engine mathematically projects that trajectory forward. 
* **The Handshake:** It validates this assumption against the Secondary Measurement (the Sensory Lines). If the knee is lost, but the thigh gap is widening, the system safely confirms the hit and triggers the MIDI note exactly when the virtual trajectory hits the floor.

## 4. The Spatial UI (Dynamic Left Leg)
To avoid immersion-breaking menus, the system utilizes the physical X-axis of the left leg as a natural UI toggle.
* **Outward Angle (Left):** The leg acts as a Hi-Hat. The absolute Y-height of the leg is mapped to a Continuous Controller (MIDI CC #4) to seamlessly transition between an open, sizzle, and closed hi-hat state.
* **Inward Angle (Right):** Mimicking moving a foot to a slave pedal, pointing the knee inwards instantly switches the leg to Double Bass mode. It stops sending CC data and engages the Inflection Tracking algorithm to trigger Kick Drum thumps (MIDI Note 36).

---
*Theory designed for the Wonder Pedal project to establish industry-grade, frictionless XR instrumental tracking.*
