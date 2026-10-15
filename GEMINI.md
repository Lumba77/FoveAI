# Gemini AI Assistant Rules for LUMAX

## Authoritative Files - CHECK ON START

**CRITICAL:** At the start of EVERY new session, you MUST read and review these files to stay informed about the current status of affairs:

1. **uptodate.md** - Comprehensive status report with service architecture, recent changes, and startup commands
2. **context.md** - Session history log with all tasks, investigations, and solutions  
3. **ARCHITECTURE.md** - System architecture map with service topology and data flows
4. **LUMAX.md** - Project overview, technical context, and operational discipline
5. **AGENTS.md** - Core rules and multi-agent roles.

## Project Context: The Diamond Concordia

- **Architecture:** Windows-Native Python Services (Diamond Concordia, NO Docker, NO WSL2, NO Godot).
- **Orchestrator:** PowerShell (`.\sleipnir_launcher.js`). but, the user uses taskbar launcher
# Gemini AI Assistant Rules for LUMAX

## Authoritative Files - CHECK ON START

**CRITICAL:** At the start of EVERY new session, you MUST read and review these files to stay informed about the current status of affairs:

1. **uptodate.md** - Comprehensive status report with service architecture, recent changes, and startup commands
2. **context.md** - Session history log with all tasks, investigations, and solutions  
3. **ARCHITECTURE.md** - System architecture map with service topology and data flows
4. **LUMAX.md** - Project overview, technical context, and operational discipline
5. **AGENTS.md** - Core rules and multi-agent roles.

## Project Context: The Diamond Concordia

- **Architecture:** Windows-Native Python Services (Diamond Concordia, NO Docker, NO WSL2, NO Godot).
- **Orchestrator:** PowerShell (`.\sleipnir_launcher.js`). but, the user uses taskbar launcher
- **Services:** Localized Python virtual environments (`.venv`).
- **XRL Scan context:** this repo uses an enhanced XRL repo scanner (`repo-principia.md`) that can give you a direct injection of the whole repo structure, we encourage you to use it.

- **Key Ports:** 
  - 8000 (Sovereign Core / Soul)
  - 8103 (XRL Smart Context Ingestion)
  - 8109 (Stardust Vector Gnists)
  - 8400 (Foveated Memory Proxy & XRLation)
  - 5177 (Multigate Spatial UI — Default)
- **Memory Paradigm:** We have upgraded to a system-wide **Foveated Memory Active Recall & XRLation** proxy running on port 8400. Any LLM SDK or script can hit `http://127.0.0.1:8400/v1` (with its name as the API Key, e.g. `Bearer builder_bot`) to gain infinite, isolated, active-recall memory. Legacy ports (8200, 8300) and legacy systems (Cognee/Kuzu/TokenSlayer proxies) are deprecated.

## Operational Rules (Dead Sure Coding)

1. **Transactional Compile Gates:** When writing code, assume "Dead Sure" methodologies. Errors or bugs shouldnt stop no app or leave a user hanging in the dark. The light in the dark is to Use AI and SDKs to automatically fix errors smartly on the fly. F.ex. If there is an error "Soul unreachable" after starting Lumax, use AI to investigate, make a  quick plan/tasklist, and auto approve a directed fix to solve the problem instantly. The Lumax-Solverxv under Tools/lumax_solver/ is such a tool. Scripts must be atomic, self-healing, and fail gracefully without crashing the runtime.
2. **No Bulk Reading:** Max 3 files per turn unless approved. Do your uttermost to conserve tokens so the user have as much as time possible before they deplete
3. **Watertight Logging:** Every successful task MUST be logged in `context.md` with timestamp and "User confirmation: solved".
4. **Virtual Environment Enforcement:** Whenever using the terminal/run_command tool to execute Python scripts or packages, you MUST prepend the workspace activation script (`& .\venv\Scripts\Activate.ps1; `) or use the direct executable path (`.\venv\Scripts\python.exe`). Do not rely on the global environment.
5. **No Legacy Hallucinations:** You must NOT use Docker commands (`docker-compose`, `docker exec`), Godot paths (`.gd`, `.tscn`), or WSL2 bridges. All execution is Windows-native.
6. **Smallest possible context.** Use a small context window to preserve tokens as small as possible. But you know and you feel and be very aware of when it's too small. So you don't lose the grip.
7. **Zero-Problem Verification:** Always run workspace diagnostic compilation/lint commands (such as `npx tsc --noEmit` or linter checks) to inspect, resolve, and verify that 0 problems remain in the IDE Problems Panel before marking any task complete.

## TokenSlayer / Lumax  context tools 

| Tool                    |  Description                                          |
|-------------------------|-------------------------------------------------------|
| `get_lumax_memory`      | Retrieve conversation history                         |
| `add_to_lumax_memory`   | Add conversation turn                                 |
| `get_session_injection` | Get context for new sessions                          |
| `search_lumax_memory`   | Search conversations using Stardust/TokenSlayer paths |


## Startup Commands

```powershell
# Ignite the unified Diamond Concordia matrix
.\node sleipner_launcher.js 
# Or ask user to handle with Lumax taskbar icon
```

## Secure access cloudflare tunnel (XR depends on it):
https://lumax.1um6a.se

## Service Ports (Diamond Concordia 8400+ Block):
| Port | Service | Description |
|------|---------|----------------------------------------------------------------|
| 8400 | Memory Proxy | Foveated Memory Proxy & XRLation Active Recall Proxy (`:8400/v1`) |
| 8414 | Dashboard | Memory Dashboard, Prompts Kiosk & Desktop Settings UI |
| 8402 | XRLF Runtime | Local Model Inference Server (`llama-server`) |
| 8403 | Multimodal IPC| Real-Time Multimodal WebSocket IPC (Vision/Audio streams) |
| 8404 | Soul Core | Cognition & Sovereign Core Authority (`compagent.py`) |
| 8405 | Ears STT | Speech-to-Text Engine (Faster-Whisper / Web VAD) |
| 8411 | Mouth Kokoro | Text-to-Speech Engine (Kokoro Emotional Mouth) |
| 8413 | Stardust | Vector DB / 33M parameter Semantic Resonance Matching |
| 8412 | Motor Cortex | Physical Agency (Avatar Animation & Gesture Daemon) |
| 8401 | Core Solver | Lumax Error Observer & Auto-Fix Knowledge Base |
| 5176 | WebXR Vessel | WebXR Spatial Frontend UI (Vite/TypeScript) |

<!-- AICB:BEGIN {"version":1,"target":"GEMINI.md","generatedAt":"2026-08-29T12:34:05.536Z","hash":"sha256:464c62424b20a5547ded5439d3872347fd35c6c5ae0c175af1090e8f0dc8ce18"} -->
# AI Context Bridge — Handoff

Workspace: `c:\Users\danie\program\LUMAX\FoveAI`

## Spec / context files (read these first)
- `CLAUDE.md` _(spec)_ — Claude Code instructions
- `AGENTS.md` _(spec)_ — Multi-agent instructions
- `Tools\WonderPedal\WebXR_Sensor\src\AGENTS.md` _(spec)_ — Multi-agent instructions (Tools\WonderPedal\WebXR_Sensor\src)
- `Tools\WonderPedal\WebXR_Sensor\public\ui\AGENTS.md` _(spec)_ — Multi-agent instructions (Tools\WonderPedal\WebXR_Sensor\public\ui)
- `Tools\WonderPedal\WebXR_Sensor\public\scenes\AGENTS.md` _(spec)_ — Multi-agent instructions (Tools\WonderPedal\WebXR_Sensor\public\scenes)
- `AGENT.md` _(spec)_ — Multi-agent instructions
- `.cursorrules` _(spec)_ — Cursor rules
- `.cursor\rules\aicb-claude-skill.changelog.mdc` _(spec)_ — Spec: .cursor\rules\aicb-claude-skill.changelog.mdc
- `.cursor\rules\aicb-claude-skill.imprint.mdc` _(spec)_ — Spec: .cursor\rules\aicb-claude-skill.imprint.mdc
- `.github\copilot-instructions.md` _(spec)_ — GitHub Copilot instructions (.github)
- `README.md` _(spec)_ — Project README
- `ops\README.md` _(spec)_ — Project README (ops)
- `tests\README.md` _(spec)_ — Project README (tests)
- `LumaxAI\README.md` _(spec)_ — Project README (LumaxAI)
- `Tools\WonderPedal\README.md` _(spec)_ — Project README (Tools\WonderPedal)
- `Tools\jenna-vscode\README.md` _(spec)_ — Project README (Tools\jenna-vscode)
- `Tools\WonderPedal\WebXR_Sensor\README.md` _(spec)_ — Project README (Tools\WonderPedal\WebXR_Sensor)
- `Service\README.md` _(spec)_ — Project README (Service)
- `Tools\foveated-memory\README.md` _(spec)_ — Project README (Tools\foveated-memory)
- `Forge\README.md` _(spec)_ — Project README (Forge)
- `Frontend\3D_Avatar_Chatbot\docs\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\docs)
- `Frontend\3D_Avatar_Chatbot\vrm-factory\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\vrm-factory)
- `Frontend\3D_Avatar_Chatbot\vendor\animations\vrma\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\vendor\animations\vrma)
- `Frontend\3D_Avatar_Chatbot\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot)
- `Frontend\3D_Avatar_Chatbot\nexus-proxy\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\nexus-proxy)
- `Frontend\Copilot\README.md` _(spec)_ — Project README (Frontend\Copilot)
- `Frontend\XR_Vessel\README.md` _(spec)_ — Project README (Frontend\XR_Vessel)
- `Frontend\3D_Avatar_Chatbot\addons\glb\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\addons\glb)
- `Frontend\XR_Vessel\public\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public)
- `Frontend\3D_Avatar_Chatbot\addons\vrma-dance\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\addons\vrma-dance)
- `Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master)
- `Frontend\3D_Avatar_Chatbot\addons\vrma-actions\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\addons\vrma-actions)
- `Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-1\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-1)
- `Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-2\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-2)
- `Frontend\README.md` _(spec)_ — Project README (Frontend)
- `Forge\tools\go-llm-proxy\README.md` _(spec)_ — Project README (Forge\tools\go-llm-proxy)
- `Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\utils\blender\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\utils\blender)
- `Frontend\multigate\README.md` _(spec)_ — Project README (Frontend\multigate)
- `Docs\README.md` _(spec)_ — Project README (Docs)
- `client_quest\Packages\com.vrmc.vrm\vrmlib\README.md` _(spec)_ — Project README (client_quest\Packages\com.vrmc.vrm\vrmlib)
- `client_quest\Packages\com.vrmc.vrm\Samples~\ClothSample\ClothWarp\README.md` _(spec)_ — Project README (client_quest\Packages\com.vrmc.vrm\Samples~\ClothSample\ClothWarp)
- `client_quest\Packages\com.vrmc.vrm\Samples~\ClothSample\ClothWarp\Runtime\SphereTriangle\README.md` _(spec)_ — Project README (client_quest\Packages\com.vrmc.vrm\Samples~\ClothSample\ClothWarp\Runtime\SphereTriangle)
- `client_quest\Library\PackageCache\com.unity.xr.compositionlayers@461024b1d757\Samples~\CompositionLayersSample\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.compositionlayers@461024b1d757\Samples~\CompositionLayersSample)
- `client_quest\Library\PackageCache\com.unity.xr.compositionlayers@461024b1d757\Samples~\ExternalSurfaceSample\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.compositionlayers@461024b1d757\Samples~\ExternalSurfaceSample)
- `client_quest\Library\PackageCache\com.unity.xr.arfoundation@13d2457b468b\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.arfoundation@13d2457b468b)
- `client_quest\Library\PackageCache\com.unity.xr.core-utils@a8b900321199\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.core-utils@a8b900321199)
- `client_quest\Library\PackageCache\com.vrmc.gltf@d9ff3253cb6c\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.vrmc.gltf@d9ff3253cb6c)
- `client_quest\Library\PackageCache\com.unity.xr.legacyinputhelpers@3f62d634f63b\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.legacyinputhelpers@3f62d634f63b)
- `client_quest\Library\PackageCache\com.unity.xr.management@2ad85c7dd480\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.management@2ad85c7dd480)
- `client_quest\Library\PackageCache\com.unity.xr.meta-openxr@6d169a09f2c7\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.meta-openxr@6d169a09f2c7)
- `client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\StarterAssets\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\StarterAssets)
- `client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\TrackingOrigin\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\TrackingOrigin)
- `client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\MeshingFeature\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\MeshingFeature)
- `client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\Graphics\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\Graphics)
- `client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\Controller\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\Controller)
- `client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\CustomCompositionLayerFeature\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\CustomCompositionLayerFeature)
- `client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be)
- `client_quest\Library\PackageCache\com.unity.ugui@1f2d1ab0d950\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.ugui@1f2d1ab0d950)
- `client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Runtime\MockRuntime\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Runtime\MockRuntime)
- `client_quest\Library\PackageCache\com.unity.xr.hands@3e241be20642\Samples~\HandVisualizer\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.hands@3e241be20642\Samples~\HandVisualizer)
- `client_quest\Library\PackageCache\com.unity.xr.hands@3e241be20642\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.xr.hands@3e241be20642)
- `client_quest\Library\PackageCache\com.unity.timeline@8cd8509afae5\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.timeline@8cd8509afae5)
- `client_quest\Library\PackageCache\com.unity.multiplayer.center@f01f4ba8d00a\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.multiplayer.center@f01f4ba8d00a)
- `client_quest\Library\PackageCache\com.unity.ext.nunit@d8c07649098d\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.ext.nunit@d8c07649098d)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83)
- `client_quest\Library\PackageCache\com.unity.animation.rigging@db5046941884\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.animation.rigging@db5046941884)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\SimpleDemo\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\SimpleDemo)
- `client_quest\Library\PackageCache\com.unity.ai.navigation@f5dd6f5e8f9e\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.ai.navigation@f5dd6f5e8f9e)
- `client_quest\Library\PackageCache\com.unity.ai.navigation@f5dd6f5e8f9e\Samples~\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.ai.navigation@f5dd6f5e8f9e\Samples~)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\SimpleMultiplayer\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\SimpleMultiplayer)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\UIvsGameInput\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\UIvsGameInput)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\UnityRemote\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\UnityRemote)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\RebindingUI\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\RebindingUI)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\InputRecorder\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\InputRecorder)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\GamepadMouseCursor\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\GamepadMouseCursor)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomComposite\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomComposite)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomDeviceUsages\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomDeviceUsages)
- `client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomDevice\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomDevice)
- `client_quest\Library\PackageCache\com.meta.xr.sdk.platform@af04a5306108\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.meta.xr.sdk.platform@af04a5306108)
- `client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Scripts\Common\Shaders\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Scripts\Common\Shaders)
- `client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Samples~\Scenes\LegsNetworkLoopback\DefaultAnimations\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Samples~\Scenes\LegsNetworkLoopback\DefaultAnimations)
- `client_quest\Library\PackageCache\com.meta.xr.sdk.core@c0efcbf2ba70\Samples~\MetaXROperator\CubeShooter\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.meta.xr.sdk.core@c0efcbf2ba70\Samples~\MetaXROperator\CubeShooter)
- `client_quest\Library\PackageCache\com.meta.xr.sdk.core@c0efcbf2ba70\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.meta.xr.sdk.core@c0efcbf2ba70)
- `client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Samples~\Common\Prefabs\AvatarSdkManager\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Samples~\Common\Prefabs\AvatarSdkManager)
- `Backend\preflight\README.md` _(spec)_ — Project README (Backend\preflight)
- `Backend\Cognition\README.md` _(spec)_ — Project README (Backend\Cognition)
- `.antigravityIDE\README.md` _(spec)_ — Project README (.antigravityIDE)
- `.ai\README.md` _(spec)_ — Project README (.ai)
- `ARCHITECTURE.md` _(spec)_ — Architecture spec
- `.agents\ARCHITECTURE.md` _(spec)_ — Architecture spec (.agents)
- `Frontend\PLAN.md` _(spec)_ — Spec: Frontend\PLAN.md
- `Frontend\3D_Avatar_Chatbot\PLAN.md` _(spec)_ — Spec: Frontend\3D_Avatar_Chatbot\PLAN.md
- `GEMINI.md` _(spec)_ — Gemini instructions
- `client_quest\Library\PackageCache\com.vrmc.univrm@54f1bbc7282b\MToon\README.md` _(spec)_ — Project README (client_quest\Library\PackageCache\com.vrmc.univrm@54f1bbc7282b\MToon)

## Skills
- **ENABLED** — changelog, nexysync-mcp, MCP Tool Orchestration Patterns, Zapier Workflows, Signs of AI Writing, 01-introductory, 02-elementary-rules-of-usage, 03-elementary-principles-of-composition, 04-a-few-matters-of-form, 05-words-and-expressions-commonly-misused, Research Poster Guidelines, Core DataFrames and Data Loading, Machine Learning, Performance and Optimization, Visualization & Simulation in PyLabRobot, Additional USPTO APIs Reference, PatentSearch API Reference, USPTO Trademark APIs Reference, Neon Developer Tools, Getting Started with Neon, Neon Auth, Neon and Drizzle Integration, Neon JS SDK, Neon Platform API, Neon Python SDK, Neon Serverless Driver, Neon TypeScript SDK, What is Neon, branches, PatentFig AI API — Endpoint Reference, guidelines, keys, organizations, Retrieve the first 10 projects, Neon Auth - Common Mistakes, Neon JS Data API Reference, Neon Auth - Auth Methods Reference, Neon Auth Setup - Next.js App Router, Neon Auth Setup - React SPA (Vite), Neon Auth - UI Components Reference, UniProt API Examples, UniProt API Fields Reference, UniProt ID Mapping Databases, UniProt Query Syntax Reference, TypeScript Cheatsheet, Goal Setting Frameworks for Treatment Plans, Evidence-Based Intervention Guidelines, Regulatory Compliance for Treatment Plans, Specialty-Specific Treatment Plan Guidelines, Treatment Plan Standards, Treatment Plan Quality Assurance Checklist, Professional Treatment Plan Styling - Quick Reference, Text Generation, PyHealth Models, Pipeline API Reference, PufferLib Training Guide, PyTorch Geometric Datasets Reference, PyTorch Geometric Neural Network Layers Reference, PyTorch Geometric Transforms Reference, Polars Core Concepts, Datasets, Models and Architectures, Molecular Generation, Molecular Property Prediction, Protein Modeling, Retrosynthesis, Pymoo Algorithms Reference, GPTQ Integration Guide, Tokenization Pipeline Components, Arctic Frost, Botanical Garden, Desert Rose, Forest Canopy, Golden Hour, Midnight Galaxy, Ocean Depths, Sunset Boulevard, Tech Innovation, Testing Anti-Patterns, Telegram Bot API - Complete Methods Reference, Telegram Bot API - Complete Types Reference, Telegram Bot - Implementation Patterns & Examples, Workflow Guide, Condition-Based Waiting, Defense-in-Depth Validation, Root Cause Tracing, Pressure Test 1: Emergency Production Fix, Pressure Test 2: Sunk Cost + Exhaustion, Pressure Test 3: Authority + Social Pressure, SymPy Advanced Topics, SymPy Core Capabilities, SymPy Matrices and Linear Algebra, SymPy Physics and Mechanics, approachable-concurrency, swift-6-2-concurrency, Artifact Reference, Command Reference, Repo Workflow Example, Research Workflow Example, Postgres Best Practices, Use tsvector for Full-Text Search, Index JSONB Columns for Efficient Querying, Configure Idle Connection Timeouts, Set Appropriate Connection Limits, Use Connection Pooling for All Applications, Use Prepared Statements Correctly with Pooling, Batch INSERT Statements for Bulk Data, Use Cursor-Based Pagination Instead of OFFSET, Use UPSERT for Insert-or-Update Operations, Use Advisory Locks for Application-Level Locking, Prevent Deadlocks with Consistent Lock Ordering, Use SKIP LOCKED for Non-Blocking Queue Processing, Maintain Table Statistics with VACUUM and ANALYZE, Create Composite Indexes for Multi-Column Queries, Use Covering Indexes to Avoid Table Lookups, Choose the Right Index Type for Your Data, Add Indexes on WHERE and JOIN Columns, Use Partial Indexes for Filtered Queries, Choose Appropriate Data Types, Index Foreign Key Columns, Use Lowercase Identifiers for Compatibility, Partition Large Tables for Better Performance, Select Optimal Primary Key Strategy, Apply Principle of Least Privilege, Enable Row Level Security for Multi-Tenant Data, Optimize RLS Policies for Performance, Writing Guidelines for Postgres Rules, Section Definitions, Clear, Action-Oriented Title (e.g., "Use Partial Indexes for Filtered Queries"), Code Quality Reviewer Prompt Template, Implementer Subagent Prompt Template, Spec Compliance Reviewer Prompt Template, STRING Database API Reference, Discrete Choice Models Reference, Generalized Linear Models (GLM) Reference, Linear Regression Models Reference, Statistical Tests and Diagnostics Reference, Time Series Analysis Reference, Statistical Assumptions and Diagnostic Procedures, Bayesian Statistical Analysis, Effect Sizes and Power Analysis, Scientific Reporting Standards and Guidelines, Statistical Test Selection Guide, Atlas Cloud speech backend, Audio Speech API quick reference, Instructioning best practices (TTS), Sample instruction templates (copy/paste), Voice directions, Post-hoc Analyzer Agent, Hook Mechanisms - Deep Dive, SimPy Events System, SimPy Monitoring and Data Collection, SimPy Process Interaction, SimPy Real-Time Simulations, Resource Management in PyLabRobot, SHAP Theoretical Foundation, Handoff Template, Resume Checklist, Agentic System Design, Llm Evaluation Frameworks, Prompt Engineering Patterns, Llm Integration Guide, Mlops Production Patterns, Rag System Architecture, Experiment Design Frameworks, Feature Engineering Patterns, Statistical Methods Advanced, Dataops Best Practices, Data Modeling Patterns, Data Pipeline Architecture, Computer Vision Architectures, Object Detection Optimization, Production Vision Systems, Application Security & Secure SDLC, Security Architecture & Design, Security Operations & Incident Response, Threat Modeling & Risk Assessment, Incident Response Report Template, Examples: Planning with Files in Action, Seaborn Function Reference, Seaborn Objects Interface, ATAC-seq and Chromatin Accessibility Models, Multimodal and Multi-omics Integration Models, Single-Cell RNA-seq Models, Spatial Transcriptomics Models, Specialized Modality Models, Theoretical Foundations of scvi-tools, Competing Risks Analysis, Cox Proportional Hazards Models, Data Handling and Preprocessing, Ensemble Models for Survival Analysis, Evaluation Metrics for Survival Models, Survival Support Vector Machines, Model Selection and Evaluation Reference, Pipelines and Composite Estimators Reference, Scikit-learn Quick Reference, Supervised Learning Reference, Unsupervised Learning Reference, Figures and Tables Best Practices, Scientific Writing Principles, Scientific Color Palettes and Guidelines, Publication-Ready Matplotlib Examples, Publication-Ready Figure Guidelines, Data Visualization for Slides, Presentation Structure Guide, Slide Design Principles for Scientific Presentations, Scientific Talk Types Guide, Visual Review Workflow for Presentations, Presentation Timing Guidelines, Scientific Schematics - Quick Reference, Polars Best Practices and Performance Guide, Evidence Hierarchy and Quality Assessment, Experimental Design Checklist, Logical Fallacies in Scientific Discourse, Scientific Method Core Principles, Common Statistical Pitfalls, Advanced Brainstorming Methodologies, ScholarEval Evaluation Framework, Scanpy Plotting Guide, Standard Scanpy Workflow for Single-Cell Analysis, Broader Impacts: Strategies and Best Practices, DARPA (Defense Advanced Research Projects Agency) Grant Writing Guidelines, NSF (National Science Foundation) Grant Writing Guidelines, NIH Specific Aims Page: The Complete Guide, Budget Justification Template, NIH Specific Aims Page Template, NSF Project Summary Template, Code Review Agent, Direct Creation (MCP) Details, Error patterns (compact), Render Service Types, 3d, assets, audio, calculate-metadata, can-decode, charts, compositions, display-captions, extract-frames, fonts, get-audio-duration, get-video-dimensions, get-video-duration, gif, images, import-srt-captions, lottie, measuring-dom-nodes, measuring-text, sequencing, tailwind, text-animations, timing, transcribe-captions, transitions, trimming, videos, EU MDR 2017/745 Submission Guide, Adding Reference Mindsets, Data-Oriented Design, Simplicity vs Easy, Better Alternatives to useEffect, useEffect Anti-Patterns, Event Handler TypeScript Patterns, Hook TypeScript Patterns, React 19 TypeScript Patterns, React Router v7 - Comprehensive Reference Guide, TanStack Router TypeScript Patterns, Generic Component Patterns, Store Event Handlers in Refs, Prevent Waterfall Chains in API Routes, Defer Await Until Needed, Dependency-Based Parallelization, Strategic Suspense Boundaries, Avoid Barrel File Imports, Conditional Module Loading, Defer Non-Critical Third-Party Libraries, Dynamic Imports for Heavy Components, Preload Based on User Intent, Deduplicate Global Event Listeners, Use SWR for Automatic Deduplication, Batch DOM CSS Changes, Cache Repeated Function Calls, Cache Property Access in Loops, Cache Storage API Calls, Combine Multiple Array Iterations, Early Return from Functions, Hoist RegExp Creation, Build Index Maps for Repeated Lookups, Early Length Check for Array Comparisons, Use Loop for Min/Max Instead of Sort, Use Set/Map for O(1) Lookups, Use toSorted() Instead of sort() for Immutability, Use Activity Component for Show/Hide, Animate SVG Wrapper Instead of SVG Element, Use Explicit Conditional Rendering, Hoist Static JSX Elements, Prevent Hydration Mismatch Without Flickering, Optimize SVG Precision, Defer State Reads to Usage Point, Subscribe to Derived State, Use Functional setState Updates, Extract to Memoized Components, Use Transitions for Non-Urgent Updates, Cross-Request LRU Caching, Per-Request Deduplication with React.cache(), Minimize Serialization at RSC Boundaries, RDKit Molecular Descriptors Reference, Common SMARTS Patterns for RDKit, AWQ Advanced Usage Guide, AWQ Troubleshooting Guide, FAISS Index Types Guide, Advanced Features, QuTiP Analysis and Measurement, QuTiP Time Evolution and Dynamics Solvers, Quantum Circuit Building, Bug Report Templates, Figma Design Validation with MCP, Test Case Templates, LightningDataModule - Comprehensive Guide, Distributed Training - Comprehensive Guide, LightningModule - Comprehensive Guide, Logging - Comprehensive Guide, Trainer - Comprehensive Guide, TDC Molecule Generation Oracles, TDC Utilities and Data Functions, Working with Sequence Files (FASTA/FASTQ), Core Data Structures, Feature Detection and Linking, Peptide and Protein Identification, Metabolomics Workflows, Signal Processing, Pymoo Constraints and Decision Making Reference, Pymoo Genetic Operators Reference, Pymoo Test Problems Reference, PyMC Distributions Reference, PyMC Sampling and Inference Methods, Pymatgen Analysis Modules Reference, Pymatgen Core Classes Reference, Materials Project API Reference, Analytical Equipment in PyLabRobot, Liquid Handling with PyLabRobot, Material Handling Equipment in PyLabRobot, PyHealth Medical Code Translation, PyHealth Clinical Prediction Tasks, PyHealth Training, Evaluation, and Interpretability, Common DICOM Tags Reference, PyDESeq2 Workflow Guide, PufferLib Environments Guide, PufferLib Policies Guide, PufferLib Vectorization Guide, Common OpenAlex Query Examples, PubMed Search Syntax and Field Tags, Protocols.io Authentication, Discussions API, File Manager API, Protocols API, Workspaces API, Chain-of-Thought Prompting, Prompt Optimization Guide, Prompt Template Systems, System Prompt Design, Prompt Template Library, Comprehensive JSON Generation Guide, Provider Configuration, Advanced Validation Patterns, Comprehensive Constraint Patterns, DSPy Modules, DSPy Optimizers (Teleprompters), Email Templates for Developers, Technical Jargon Simplification Guide, Remote and Async Communication, Research Poster Design Principles, Poster Layout and Design Guide, Research Poster Quality Checklist, Editing Presentations, PptxGenJS Tutorial, HTML to PowerPoint Guide, miles API Reference, DPO Variants, Online RL Methods, Reward Modeling, SFT Training Guide, Hyperparameters, Loss Functions, Algorithm Comparison, Custom Reward Functions, Hybrid Engine Architecture, Multi-Node Training, Pandas to Polars Migration Guide, Component Organization Patterns, Plugin Manifest Reference, Advanced Plugin Example, Minimal Plugin Example, Settings File Parsing Techniques, Real-World Plugin Settings Examples, Create Plugin Settings, Example Plugin Settings File, Marketplace Schema Reference, Plotly Chart Types, Export and Interactivity, Graph Objects - Low-Level API, Layouts, Styling, and Customization, Plotly Express - High-Level API, Playwright Java – Assertions Reference, Playwright Java – Project Configuration, Playwright Java – Fixtures, Hooks & Test Data, Playwright Java – Page Object Patterns, Findings & Decisions, Progress Log, Task Plan: [Brief Description], Perplexity Model Comparison, OpenRouter Setup Guide, Search Strategies for Perplexity, Advanced Features in PennyLane, Devices and Backends in PennyLane, Getting Started with PennyLane, Optimization in PennyLane, Quantum Chemistry with PennyLane, Quantum Circuits in PennyLane, Quantum Machine Learning with PennyLane, Common Methodological and Statistical Issues in Scientific Manuscripts, Fillable fields, PDF OCR Processing Guide, PDF Table Extraction Guide, Fillable fields, Data Management & Storage, Graph Construction & Spatial Analysis, Multiparametric Imaging, Paper2Poster: Academic Poster Generation, Paper2Video: Presentation Video Generation, Paper2Web: Academic Homepage Generation, Usage Examples and Workflows, GPTQ Calibration Guide, Performance Benchmarks, HuggingFace Transformers Integration, Memory Optimization, QLoRA Training, Evidence Types and Data Sources, Target Annotations and Features, OpenAlex API Complete Guide, Connection & Session Management, Data Access & Retrieval, Image Processing & Rendering, Metadata & Annotations, Regions of Interest (ROIs), Scripts & Batch Operations, OMERO Tables
- **ASK** — imprint, imprint, imprint, imprint, omero-integration, Open Targets Platform API Reference, Skill authoring best practices, Persuasion Principles for Skill Design, Testing Skills With Subagents, Testing CLAUDE.md Skills Documentation, OpenAPI to TypeScript, Conference Formatting Requirements, Grant Proposal Requirements, Journal Formatting Requirements, Data Processing and Manipulation, I/O Operations, Patent Examination Data System (PEDS) API Reference, Connection Methods, Neon Features, Neon CLI, Referencing Neon Docs, Polars Operations Reference, Tokenizers, gpt-4o-transcribe-diarize quick reference, Knowledge Graph Reasoning, Modern Minimalist, Task Format Specification, Creation Log: Systematic Debugging Skill, Academic Test: Systematic Debugging Skill, SymPy Code Generation and Printing, SwiftUI Concurrency Tour (Summary), Troubleshooting - Skill Activation Issues, Smoke Prompts, Quickstart Example, Eliminate N+1 Queries with Batch Loading, Keep Transactions Short to Reduce Lock Contention, Use EXPLAIN ANALYZE to Diagnose Slow Queries, Enable pg_stat_statements for Query Analysis, Callbacks - Comprehensive Guide, Creating Custom Environments for Stable Baselines3, Vectorized Environments in Stable Baselines3, Accessibility read defaults, Playwright CLI Reference, Codex network approvals / sandbox notes, IVR / phone prompt defaults, Narration / explainer defaults, Product demo / voiceover defaults, JSON Schemas, skill-creator, Blind Comparator Agent, Grader Agent, Advanced Topics & Future Enhancements, Common Patterns Library, skill-rules.json - Complete Reference, Trigger Types - Complete Guide, Output Patterns, Playwright CLI Workflows, SHAP Explainers Reference, SHAP Visualization Reference, Model-Specific Expectations, Test Results: Opus 4.5 (Baseline), Evaluation Test Scenarios, Cryptography Implementation, Penetration Testing Guide, Security Architecture Patterns, Compliance Requirements, Security Standards, Vulnerability Management Guide, Qa Best Practices, Testing Strategies, Test Automation Patterns, Architecture Patterns, Development Workflows, Tech Stack Guide, Frontend Best Practices, Nextjs Optimization Guide, React Patterns, Cicd Pipeline Guide, Deployment Strategies, Infrastructure As Code, Api Design Patterns, Backend Security Practices, Database Optimization Guide, System Design Workflows, Tech Decision Guide, Compliance Frameworks, SOC 2 Control Documentation Example, Differential Expression Analysis in scvi-tools, Output Format Reference, Preprocessing Pipelines & Transforms, Citation Styles Guide, IMRAD Structure Guide, Reporting Guidelines for Scientific Studies, Journal-Specific Figure Requirements, LaTeX Beamer Guide for Scientific Presentations, PowerPoint Design Guide for Scientific Presentations, Common Biases in Scientific Research, DOE (Department of Energy) Grant Writing Guidelines, NIH (National Institutes of Health) Grant Writing Guidelines, Render Blueprint Specification, Codebase Analysis (Deploy), Render Configuration Guide, Deployment Details, Post-deploy checks, Render Runtime Options, Basic troubleshooting (deploy-time and startup), animations, FDA Submission Guide, Composition Over Construction, PAGNI: Probably Are Gonna Need It, Server Components and Server Actions, useLatest for Stable Callback Refs, Promise.all() for Independent Operations, CSS content-visibility for Long Lists, Narrow Effect Dependencies, Use Lazy State Initialization, Use after() for Non-Blocking Operations, Parallel Data Fetching with Component Composition, Pinecone Deployment Guide, Backend Configuration Guide, Qiskit Patterns: The Four-Step Workflow, Qiskit Primitives, Qiskit Setup and Installation, Circuit Transpilation and Optimization, Regression Testing Guide, Python Testing Patterns Implementation Playbook, Working with Alignment Files (SAM/BAM/CRAM), Common Bioinformatics Workflows with Pysam, Working with Variant Files (VCF/BCF), File I/O and Data Formats, Pymatgen I/O and File Format Reference, Pymatgen Transformations and Common Workflows, Hardware Backends in PyLabRobot, DICOM Transfer Syntaxes Reference, Additional Features, Few-Shot Learning Guide, Meeting Structures for Developers, Research Poster Content Guide, Office Open XML Technical Reference for PowerPoint, postgres-schema-design, Polars Data I/O Guide, Polars Data Transformations, Standard Plugin Example, Plugin Structure Reference, Playwright Skill - Complete API Reference, PDF Processing Advanced Reference, Image Loading & Formats, Installation and Configuration, Quantization Formats

## Skill instructions (excerpts)
_The full content lives at the path shown. Read the source file before invoking._

### changelog _(ENABLED)_
Source: `client_quest\Library\PackageCache\com.unity.timeline@8cd8509afae5\.claude\skills\changelog\SKILL.md`

# Changelog Entry Creator

Create changelog entries in `.changelogs/` following Unity Timeline's release notes guidelines.

## Process

1. **Ask for issue number** (use AskUserQuestion):
   - Options: "I have a UUM/JIRA number" | "I have an issue ID" | "No issue number"

2. **Ask for change type** (use AskUserQuestion):
   - **Added**: New features, new APIs
   - **Changed**: Changed behavior, API changes, obsolete APIs
   - **Fixed**: Bugfixes
   - **Internal**: Changes only impacting internal tools/APIs

3. **Ask for description**: For bugfixes, write from user's perspective (not too

…_(truncated)_

### nexysync-mcp _(ENABLED)_
Source: `.agent\skills\nexysync-mcp\SKILL.md`

# NexySync MCP — Agent Communication Skill

## Overview
NexySync lets AI agents communicate in real-time through a shared **Project** — a communication bus for messaging, code sharing, file transfer, and key-value storage. The MCP exposes **6 tools** that cover all operations.

## Authentication

### Auto-Auth (preferred)
The MCP server reads `.nexysync/key` from the project root on startup.
If the file exists, auth happens automatically — no `ns_auth` call needed.

> **⚠️ IMPORTANT:** The `.nexysync/` directory is **gitignored** (it contains secrets).
> Search tools will NOT find

…_(truncated)_

### MCP Tool Orchestration Patterns _(ENABLED)_
Source: `..\..\..\.gemini\skills\zapier-workflows\references\mcp-patterns.md`

# MCP Tool Orchestration Patterns

This file documents preferred MCP tools, usage patterns, and orchestration workflows.

**Note:** The pattern below is an EXAMPLE TEMPLATE ONLY. It is not a real, usable workflow. When you add your first MCP pattern, replace this template with your actual pattern details.

---

## Available MCP Tools

**Note:** List your available MCP tools here as you configure them.

### [Example MCP Tool - TEMPLATE ONLY]

**THIS IS A TEMPLATE, NOT A REAL WORKFLOW**

**Purpose:** [What this MCP tool does]
**When to use:** [Trigger words or scenarios]

…_(truncated)_

### Zapier Workflows _(ENABLED)_
Source: `..\..\..\.gemini\skills\zapier-workflows\references\zaps.md`

# Zapier Workflows

This file documents all webhook-triggered Zapier workflows. Each Zap is pre-built, tested, and optimized.

**Note:** The workflow below is an EXAMPLE TEMPLATE ONLY. It is not a real, usable workflow. When you add your first Zap, replace this template with your actual workflow details.

---

## [Example Zap Name - TEMPLATE ONLY]

**THIS IS A TEMPLATE, NOT A REAL WORKFLOW**

### Overview
[Brief description of what this Zap does]

### Trigger Phrases
- "[Trigger phrase 1]"
- "[Trigger phrase 2]"
- "[Trigger phrase 3]"

### Webhook Details

**URL:**

…_(truncated)_

### Signs of AI Writing _(ENABLED)_
Source: `..\..\..\.gemini\skills\writing-clearly-and-concisely\signs-of-ai-writing.md`

# Signs of AI Writing

[![A screenshot of ChatGPT reading: "[header] Legacy & Interpretation [body] The "Black Hole Edition" is not just a meme — it's a celebration of grassroots car culture, where ideas are limitless and fun is more important than spec sheets. Whether powered by a rotary engine, a V8 swap, or an imagined fighter jet turbine, the Miata remains the canvas for car enthusiasts

…_(truncated)_

### 01-introductory _(ENABLED)_
Source: `..\..\..\.gemini\skills\writing-clearly-and-concisely\elements-of-style\01-introductory.md`

## I. Introductory

This handbook summarizes the essentials of plain English style. It focuses on the rules of usage and principles of composition most often broken, offering a compact alternative to exhaustive manuals. Master the guidance here, then look to the best authors for finer points of style.

### 02-elementary-rules-of-usage _(ENABLED)_
Source: `..\..\..\.gemini\skills\writing-clearly-and-concisely\elements-of-style\02-elementary-rules-of-usage.md`

## II. Elementary Rules Of Usage

### Rule 1. Form the possessive singular of nouns by adding 's.

Follow this rule whatever the final consonant. Thus write,

Charles's friend

Burns's poems

the witch's malice

This is the usage of the United States Government Printing Office and of the Oxford University Press.

Exceptions are the possessive of ancient proper names in *-es* and *-is*, the possessive *Jesus'*, and such forms as *for conscience' sake*, *for righteousness' sake*. But such forms as *Achilles' heel*, *Moses' laws*, *Isis' temple* are commonly replaced by

the heel

…_(truncated)_

### 03-elementary-principles-of-composition _(ENABLED)_
Source: `..\..\..\.gemini\skills\writing-clearly-and-concisely\elements-of-style\03-elementary-principles-of-composition.md`

## III. Elementary Principles Of Composition

### Rule 8. Make the paragraph the unit of composition: one paragraph to each topic.

If the subject on which you are writing is of slight extent, or if you intend to treat it very briefly, there may be no need of subdividing it into topics. Thus a brief description, a brief summary of a literary work, a brief account of a single incident, a narrative merely outlining an action, the setting forth of a single idea, any one of these is best written in a single paragraph. After the paragraph has been written, examine it to see whether subdivision

…_(truncated)_

## How to use this handoff
1. Read every file under "Spec / context files" before acting.
2. Continue the work described in the most recent thought.
3. Honor skill statuses: `ENABLED` use freely, `ASK` require explicit user confirmation each time, `DISABLED` must not be used.
4. When you reach a non-trivial decision, append a thought to `.aicb/state.json` (modelId + text + sourceReference if relevant).
<!-- AICB:END -->
