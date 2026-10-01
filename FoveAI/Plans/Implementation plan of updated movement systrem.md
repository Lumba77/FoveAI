# Implementation Plan: Native Motor Cortex Integration

## Goal
To implement true, organic physical agency for Jen by giving her local model (Gemma 4 / LM Studio) native OpenAI-compatible Tool Calling. We will bypass the bulky LM Studio Python SDK and directly inject her "motor functions" (Walk, Emote, Micro-gestures) into the core `compagent.py` HTTP streaming pipeline. This ensures her motor commands execute instantly while preserving the Ratatosk privacy veil and the Diamond Concordia architecture.

## How it Works
1. When Jen speaks, the backend constructs the standard `/v1/chat/completions` HTTP request but appends a `tools` JSON array defining her physical capabilities.
2. The local LLM will natively output a `tool_calls` JSON object instead of (or alongside) raw text.
3. The `compagent.py` stream parser will intercept these tool calls and instantly fire them to `motor_cortex.py`.
4. `motor_cortex.py` will broadcast an SSE `motor_action` event straight to the Chrome Extension/WebXR Vessel, resulting in zero-latency physical movement in the room.

## Proposed Changes

### 1. `Backend/Cognition/motor_cortex.py`
[MODIFY] Refine the file to output strict OpenAI-compatible JSON Schemas for the tools:
- `walk_forward(distance)`
- `walk_to_target(target)`
- `change_emotion(emotion, intensity)`
- `trigger_micro_gesture(gesture)`

### 2. `Backend/Cognition/compagent.py`
[MODIFY] Locate the `httpx.AsyncClient().stream()` loop. 
- Inject the `tools` array from `motor_cortex.py` into the HTTP payload if `LUMAX_COGNITIVE_MODE == "local"`.
- Update the chunk parser to watch for `"tool_calls"` arrays in the stream.
- When a full tool call is parsed, execute it via `motor_cortex` and yield the SSE motor event to the frontend.

### 3. `Frontend/XR_Vessel/src/...` (WebXR or Extension)
[MODIFY] Update the frontend event listener to intercept `motor_action` SSE streams and route them to `MovementEngine.ts`.

## Open Questions
> [!IMPORTANT]
> The AntiGravity Chrome Extension you installed opens up massive possibilities! We can easily route these SSE motor events directly through the extension's MCP bridge or WebSockets, giving us ultra-fast low-latency bridging between the backend logic and the browser's WebXR renderer. Should we use the existing `compagent.py` SSE stream for now, or would you like to explore bridging it directly through the Chrome Extension?
