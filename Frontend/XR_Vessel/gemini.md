Here are the specific manufacturing instructions for Gemini Queen to execute Phase A and B:



1\. Consolidate Dependencies

Gemini Queen must strip the existing package.json of any server-side dependencies and add the browser-native stack.  



Action: Replace current dependencies with:



"three": "^0.184.0"



&#x20; 



"@pixiv/three-vrm": "^3.5.2"



&#x20; 



"dexie": "^4.0.11" (For permanent local memory)  



"@mlc-ai/webllm": "^0.2.46" (For the local GPU-accelerated brain)  



2\. Implement the "Matchbox" Memory (Phase A)

Instead of the unreachable Soul Upstream, create a native database file: src/network/LocalMemory.ts\[cite: 1, 13].



Instruction: Use Dexie.js to create a local store for conversations and martinustheology.  



Robustness Rule: Initialize with await navigator.storage.persist() to prevent the browser from clearing data when disk space is low.  



Structure: Store every interaction from the "Heretical Mask" locally before any "Leveling" occurs in the cloud.  



3\. Initialize the Browser Brain (Phase B)

Create src/network/LocalBrain.ts to leverage your RTX 4060 directly through the browser.  



Instruction: Implement WebLLM to load the Llama-3.2-1B-Instruct model.  



Hardware Mapping: Ensure the engine is configured to use WebGPU.  



Plausible Deniability Logic: The Local Brain handles all "intimate" or "heretical" dialogue; it only calls the Gemini Cloud API via a fetch request for high-level philosophical expansions.  



4\. Rewire the Vessel Hub (src/main.ts)

Gemini Queen must modify the entry point to connect these new organs to the existing "Body".  



Step 1: Remove the SoulBridge WebSocket connection (Port 8000).  



Step 2: Listen for audio events from AuralAwareness.ts.  



Step 3: Route text from the local brain to the AvatarManager.setLipSync() function to animate your VRM character in real-time.  



Step 4: Ensure the RoomSpatialContext is fed into the local brain's prompt so the AI knows its position in your physical room\[cite: 1, 12].



5\. Visual "Melting" Protocol

Gemini Queen should optimize the Environment.ts for the "melting" effect.  



Instruction: Keep the WebGLRenderer alpha enabled and the clear color at 0 for perfect passthrough.  



Action: Apply a Three.js NoiseShader to the VRM model's edges within AvatarManager.ts to achieve the requested visual dissolution into the environment\[cite: 1, 9]

