<!-- AICB:BEGIN {"version":1,"target":".agent/AGENTS.md","generatedAt":"2026-09-02T10:34:11.706Z","hash":"sha256:a2fc10e65916953e0d3d313b3b2419b4be4e21648d1f3ad89b8a38653291afa8"} -->
# AI Context Bridge — Handoff

Workspace: `c:\Users\danie\program\LUMAX`

## Spec / context files (read these first)
- `AGENTS.md` _(spec)_ — Multi-agent instructions
- `Tools\WonderPedal\WebXR_Sensor\src\AGENTS.md` _(spec)_ — Multi-agent instructions (Tools\WonderPedal\WebXR_Sensor\src)
- `Tools\WonderPedal\WebXR_Sensor\public\ui\AGENTS.md` _(spec)_ — Multi-agent instructions (Tools\WonderPedal\WebXR_Sensor\public\ui)
- `Tools\WonderPedal\WebXR_Sensor\public\scenes\AGENTS.md` _(spec)_ — Multi-agent instructions (Tools\WonderPedal\WebXR_Sensor\public\scenes)
- `AGENT.md` _(spec)_ — Multi-agent instructions
- `.cursorrules` _(spec)_ — Cursor rules
- `README.md` _(spec)_ — Project README
- `.ai\README.md` _(spec)_ — Project README (.ai)
- `.antigravityIDE\README.md` _(spec)_ — Project README (.antigravityIDE)
- `Backend\preflight\README.md` _(spec)_ — Project README (Backend\preflight)
- `Build\Web_Vessel\README.md` _(spec)_ — Project README (Build\Web_Vessel)
- `Frontend\Copilot\README.md` _(spec)_ — Project README (Frontend\Copilot)
- `Frontend\README.md` _(spec)_ — Project README (Frontend)
- `Frontend\multigate\README.md` _(spec)_ — Project README (Frontend\multigate)
- `Build\Web_Vessel\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-1\README.md` _(spec)_ — Project README (Build\Web_Vessel\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-1)
- `Frontend\XR_Vessel\README.md` _(spec)_ — Project README (Frontend\XR_Vessel)
- `Frontend\XR_Vessel\webvm_source\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\webvm_source)
- `Build\Web_Vessel\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-2\README.md` _(spec)_ — Project README (Build\Web_Vessel\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-2)
- `Frontend\XR_Vessel\public\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public)
- `Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master)
- `Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\utils\blender\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\utils\blender)
- `Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-1\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-1)
- `Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-2\README.md` _(spec)_ — Project README (Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-2)
- `Build\Web_Vessel\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\README.md` _(spec)_ — Project README (Build\Web_Vessel\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master)
- `Build\Web_Vessel\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\utils\blender\README.md` _(spec)_ — Project README (Build\Web_Vessel\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\utils\blender)
- `Frontend\3D_Avatar_Chatbot\vrm-factory\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\vrm-factory)
- `Frontend\3D_Avatar_Chatbot\vendor\animations\vrma\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\vendor\animations\vrma)
- `Frontend\3D_Avatar_Chatbot\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot)
- `Frontend\3D_Avatar_Chatbot\nexus-proxy\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\nexus-proxy)
- `Frontend\3D_Avatar_Chatbot\docs\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\docs)
- `Frontend\3D_Avatar_Chatbot\addons\vrma-dance\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\addons\vrma-dance)
- `Frontend\3D_Avatar_Chatbot\addons\glb\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\addons\glb)
- `Frontend\3D_Avatar_Chatbot\addons\vrma-actions\README.md` _(spec)_ — Project README (Frontend\3D_Avatar_Chatbot\addons\vrma-actions)
- `outputs\README.md` _(spec)_ — Project README (outputs)
- `Tools\WonderPedal\README.md` _(spec)_ — Project README (Tools\WonderPedal)
- `Tools\XRLF-1.0-source\README.md` _(spec)_ — Project README (Tools\XRLF-1.0-source)
- `Tools\WonderPedal\WebXR_Sensor\README.md` _(spec)_ — Project README (Tools\WonderPedal\WebXR_Sensor)
- `Tools\WonderPedal\WonderPedalUnity\vrdm\README.md` _(spec)_ — Project README (Tools\WonderPedal\WonderPedalUnity\vrdm)
- `Tools\WonderPedal\WonderPedalUnity\vrdm\Packages\Melanchall.DryWetMidi.6.1.3\README.md` _(spec)_ — Project README (Tools\WonderPedal\WonderPedalUnity\vrdm\Packages\Melanchall.DryWetMidi.6.1.3)
- `Tools\XRLF-1.0-source\foveated-memory\README.md` _(spec)_ — Project README (Tools\XRLF-1.0-source\foveated-memory)
- `tests\README.md` _(spec)_ — Project README (tests)
- `Tools\XRLF 1.0 dev\foveated-memory\README.md` _(spec)_ — Project README (Tools\XRLF 1.0 dev\foveated-memory)
- `Tools\XRLF 1.0 dev\README.md` _(spec)_ — Project README (Tools\XRLF 1.0 dev)
- `Tools\XRLF 1.0 dev\_forge\README.md` _(spec)_ — Project README (Tools\XRLF 1.0 dev\_forge)
- `outputs\checkpoint-60\README.md` _(spec)_ — Project README (outputs\checkpoint-60)
- `Tools\foveated-memory\README.md` _(spec)_ — Project README (Tools\foveated-memory)
- `Tools\jenna-vscode\README.md` _(spec)_ — Project README (Tools\jenna-vscode)
- `Backend\Cognition\README.md` _(spec)_ — Project README (Backend\Cognition)
- `Service\README.md` _(spec)_ — Project README (Service)
- `ops\README.md` _(spec)_ — Project README (ops)
- `Nursery\outputs\README.md` _(spec)_ — Project README (Nursery\outputs)
- `Nursery\outputs\checkpoint-60\README.md` _(spec)_ — Project README (Nursery\outputs\checkpoint-60)
- `Forge\tools\go-llm-proxy\README.md` _(spec)_ — Project README (Forge\tools\go-llm-proxy)
- `Forge\README.md` _(spec)_ — Project README (Forge)
- `Forge\scratch\TokenSlayer\README.md` _(spec)_ — Project README (Forge\scratch\TokenSlayer)
- `LumaxAI\README.md` _(spec)_ — Project README (LumaxAI)
- `Docs\README.md` _(spec)_ — Project README (Docs)
- `ARCHITECTURE.md` _(spec)_ — Architecture spec
- `.agents\ARCHITECTURE.md` _(spec)_ — Architecture spec (.agents)
- `Frontend\PLAN.md` _(spec)_ — Spec: Frontend\PLAN.md
- `Frontend\3D_Avatar_Chatbot\PLAN.md` _(spec)_ — Spec: Frontend\3D_Avatar_Chatbot\PLAN.md
- `CLAUDE.md` _(spec)_ — Claude Code instructions
- `GEMINI.md` _(spec)_ — Gemini instructions
- `.cursor\rules\aicb-claude-skill.imprint.mdc` _(spec)_ — Spec: .cursor\rules\aicb-claude-skill.imprint.mdc
- `.cursor\rules\aicb-claude-skill.changelog.mdc` _(spec)_ — Spec: .cursor\rules\aicb-claude-skill.changelog.mdc
- `.agent\AGENTS.md` _(spec)_ — Multi-agent instructions (.agent)
- `.windsurfrules` _(spec)_ — Windsurf rules
- `Training\outputs\xrlf_router_lora\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_lora)
- `Training\outputs\xrlf_draft_lora\README.md` _(spec)_ — Project README (Training\outputs\xrlf_draft_lora)
- `Training\outputs\xrlf_router_lora\checkpoint-100\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_lora\checkpoint-100)
- `Training\outputs\xrlf_router_lora\checkpoint-272\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_lora\checkpoint-272)
- `Training\outputs\xrlf_router_lora\adapter\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_lora\adapter)
- `Training\outputs\xrlf_router_lora\checkpoint-200\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_lora\checkpoint-200)
- `Training\outputs\xrlf_draft_lora\checkpoint-200\README.md` _(spec)_ — Project README (Training\outputs\xrlf_draft_lora\checkpoint-200)
- `Training\outputs\xrlf_draft_lora\checkpoint-204\README.md` _(spec)_ — Project README (Training\outputs\xrlf_draft_lora\checkpoint-204)
- `Training\outputs\xrlf_draft_lora\checkpoint-100\README.md` _(spec)_ — Project README (Training\outputs\xrlf_draft_lora\checkpoint-100)
- `Training\outputs\xrlf_draft_lora\adapter\README.md` _(spec)_ — Project README (Training\outputs\xrlf_draft_lora\adapter)
- `FoveAI\CLAUDE.md` _(spec)_ — Claude Code instructions (FoveAI)
- `FoveAI\Tools\WonderPedal\WebXR_Sensor\public\scenes\AGENTS.md` _(spec)_ — Multi-agent instructions (FoveAI\Tools\WonderPedal\WebXR_Sensor\public\scenes)
- `FoveAI\Tools\WonderPedal\WebXR_Sensor\public\ui\AGENTS.md` _(spec)_ — Multi-agent instructions (FoveAI\Tools\WonderPedal\WebXR_Sensor\public\ui)
- `FoveAI\Tools\WonderPedal\WebXR_Sensor\src\AGENTS.md` _(spec)_ — Multi-agent instructions (FoveAI\Tools\WonderPedal\WebXR_Sensor\src)
- `FoveAI\AGENTS.md` _(spec)_ — Multi-agent instructions (FoveAI)
- `FoveAI\GEMINI.md` _(spec)_ — Gemini instructions (FoveAI)
- `FoveAI\AGENT.md` _(spec)_ — Multi-agent instructions (FoveAI)
- `FoveAI\.cursorrules` _(spec)_ — Cursor rules (FoveAI)
- `FoveAI\.cursor\rules\aicb-claude-skill.imprint.mdc` _(spec)_ — Spec: FoveAI\.cursor\rules\aicb-claude-skill.imprint.mdc
- `FoveAI\.cursor\rules\aicb-claude-skill.changelog.mdc` _(spec)_ — Spec: FoveAI\.cursor\rules\aicb-claude-skill.changelog.mdc
- `Training\outputs\xrlf_summarizer_lora\README.md` _(spec)_ — Project README (Training\outputs\xrlf_summarizer_lora)
- `Training\outputs\xrlf_summarizer_lora\checkpoint-100\README.md` _(spec)_ — Project README (Training\outputs\xrlf_summarizer_lora\checkpoint-100)
- `Training\outputs\xrlf_summarizer_lora\checkpoint-114\README.md` _(spec)_ — Project README (Training\outputs\xrlf_summarizer_lora\checkpoint-114)
- `Training\outputs\xrlf_summarizer_lora\adapter\README.md` _(spec)_ — Project README (Training\outputs\xrlf_summarizer_lora\adapter)
- `Training\outputs\xrlf_router_coder1.5b_lora\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_coder1.5b_lora)
- `Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-273\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-273)
- `Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-200\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-200)
- `Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-364\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-364)
- `Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-352\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-352)
- `Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-300\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-300)
- `Training\outputs\xrlf_router_coder1.5b_lora\adapter\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_coder1.5b_lora\adapter)
- `Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-100\README.md` _(spec)_ — Project README (Training\outputs\xrlf_router_coder1.5b_lora\checkpoint-100)
- `Training\outputs\xrlf_coder_mtp_lora\README.md` _(spec)_ — Project README (Training\outputs\xrlf_coder_mtp_lora)
- `Training\outputs\xrlf_coder_mtp_lora\adapter\README.md` _(spec)_ — Project README (Training\outputs\xrlf_coder_mtp_lora\adapter)
- `Training\outputs\xrlf_coder_mtp_lora\checkpoint-50\README.md` _(spec)_ — Project README (Training\outputs\xrlf_coder_mtp_lora\checkpoint-50)
- `Training\outputs\xrlf_coder_mtp_lora\checkpoint-87\README.md` _(spec)_ — Project README (Training\outputs\xrlf_coder_mtp_lora\checkpoint-87)
- `FoveAI\README.md` _(spec)_ — Project README (FoveAI)
- `FoveAI\_forge\README.md` _(spec)_ — Project README (FoveAI\_forge)
- `FoveAI\Tools\WonderPedal\README.md` _(spec)_ — Project README (FoveAI\Tools\WonderPedal)
- `FoveAI\Tools\WonderPedal\WebXR_Sensor\README.md` _(spec)_ — Project README (FoveAI\Tools\WonderPedal\WebXR_Sensor)
- `FoveAI\tests\README.md` _(spec)_ — Project README (FoveAI\tests)
- `FoveAI\Tools\foveated-memory\README.md` _(spec)_ — Project README (FoveAI\Tools\foveated-memory)
- `FoveAI\Tools\jenna-vscode\README.md` _(spec)_ — Project README (FoveAI\Tools\jenna-vscode)
- `FoveAI\Service\README.md` _(spec)_ — Project README (FoveAI\Service)
- `FoveAI\ops\README.md` _(spec)_ — Project README (FoveAI\ops)
- `FoveAI\LumaxAI\README.md` _(spec)_ — Project README (FoveAI\LumaxAI)
- `FoveAI\client_quest\Packages\com.vrmc.vrm\vrmlib\README.md` _(spec)_ — Project README (FoveAI\client_quest\Packages\com.vrmc.vrm\vrmlib)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\StarterAssets\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\StarterAssets)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\MeshingFeature\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\MeshingFeature)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\Graphics\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\Graphics)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\TrackingOrigin\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\TrackingOrigin)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\CustomCompositionLayerFeature\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\CustomCompositionLayerFeature)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\Controller\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Samples~\Controller)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Runtime\MockRuntime\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.openxr@b5b77b4027be\Runtime\MockRuntime)
- `FoveAI\client_quest\Library\PackageCache\com.vrmc.gltf@d9ff3253cb6c\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.vrmc.gltf@d9ff3253cb6c)
- `FoveAI\client_quest\Library\PackageCache\com.vrmc.univrm@54f1bbc7282b\MToon\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.vrmc.univrm@54f1bbc7282b\MToon)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.legacyinputhelpers@3f62d634f63b\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.legacyinputhelpers@3f62d634f63b)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.core-utils@a8b900321199\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.core-utils@a8b900321199)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.hands@3e241be20642\Samples~\HandVisualizer\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.hands@3e241be20642\Samples~\HandVisualizer)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.hands@3e241be20642\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.hands@3e241be20642)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.management@2ad85c7dd480\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.management@2ad85c7dd480)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.meta-openxr@6d169a09f2c7\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.meta-openxr@6d169a09f2c7)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.compositionlayers@461024b1d757\Samples~\CompositionLayersSample\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.compositionlayers@461024b1d757\Samples~\CompositionLayersSample)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.compositionlayers@461024b1d757\Samples~\ExternalSurfaceSample\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.compositionlayers@461024b1d757\Samples~\ExternalSurfaceSample)
- `FoveAI\client_quest\Library\PackageCache\com.unity.ugui@1f2d1ab0d950\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.ugui@1f2d1ab0d950)
- `FoveAI\client_quest\Library\PackageCache\com.unity.xr.arfoundation@13d2457b468b\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.xr.arfoundation@13d2457b468b)
- `FoveAI\client_quest\Library\PackageCache\com.unity.timeline@8cd8509afae5\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.timeline@8cd8509afae5)
- `FoveAI\client_quest\Library\PackageCache\com.unity.multiplayer.center@f01f4ba8d00a\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.multiplayer.center@f01f4ba8d00a)
- `FoveAI\client_quest\Library\PackageCache\com.unity.ext.nunit@d8c07649098d\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.ext.nunit@d8c07649098d)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\UnityRemote\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\UnityRemote)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\UIvsGameInput\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\UIvsGameInput)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\SimpleMultiplayer\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\SimpleMultiplayer)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\SimpleDemo\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\SimpleDemo)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\RebindingUI\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\RebindingUI)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\InputRecorder\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\InputRecorder)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\GamepadMouseCursor\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\GamepadMouseCursor)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomDeviceUsages\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomDeviceUsages)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomComposite\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomComposite)
- `FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomDevice\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.inputsystem@21a28c3a6c83\Samples~\CustomDevice)
- `FoveAI\client_quest\Library\PackageCache\com.unity.ai.navigation@f5dd6f5e8f9e\Samples~\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.ai.navigation@f5dd6f5e8f9e\Samples~)
- `FoveAI\client_quest\Library\PackageCache\com.unity.ai.navigation@f5dd6f5e8f9e\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.ai.navigation@f5dd6f5e8f9e)
- `FoveAI\client_quest\Library\PackageCache\com.unity.animation.rigging@db5046941884\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.unity.animation.rigging@db5046941884)
- `FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.platform@af04a5306108\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.platform@af04a5306108)
- `FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.core@c0efcbf2ba70\Samples~\MetaXROperator\CubeShooter\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.core@c0efcbf2ba70\Samples~\MetaXROperator\CubeShooter)
- `FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Scripts\Common\Shaders\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Scripts\Common\Shaders)
- `FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Samples~\Scenes\LegsNetworkLoopback\DefaultAnimations\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Samples~\Scenes\LegsNetworkLoopback\DefaultAnimations)
- `FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Samples~\Common\Prefabs\AvatarSdkManager\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.avatars@45b03b85dc05\Samples~\Common\Prefabs\AvatarSdkManager)
- `FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.core@c0efcbf2ba70\README.md` _(spec)_ — Project README (FoveAI\client_quest\Library\PackageCache\com.meta.xr.sdk.core@c0efcbf2ba70)
- `FoveAI\client_quest\Packages\com.vrmc.vrm\Samples~\ClothSample\ClothWarp\README.md` _(spec)_ — Project README (FoveAI\client_quest\Packages\com.vrmc.vrm\Samples~\ClothSample\ClothWarp)
- `FoveAI\client_quest\Packages\com.vrmc.vrm\Samples~\ClothSample\ClothWarp\Runtime\SphereTriangle\README.md` _(spec)_ — Project README (FoveAI\client_quest\Packages\com.vrmc.vrm\Samples~\ClothSample\ClothWarp\Runtime\SphereTriangle)
- `FoveAI\Forge\README.md` _(spec)_ — Project README (FoveAI\Forge)
- `FoveAI\Frontend\Copilot\README.md` _(spec)_ — Project README (FoveAI\Frontend\Copilot)
- `FoveAI\Forge\tools\go-llm-proxy\README.md` _(spec)_ — Project README (FoveAI\Forge\tools\go-llm-proxy)
- `FoveAI\Frontend\README.md` _(spec)_ — Project README (FoveAI\Frontend)
- `FoveAI\Docs\README.md` _(spec)_ — Project README (FoveAI\Docs)
- `FoveAI\Frontend\XR_Vessel\README.md` _(spec)_ — Project README (FoveAI\Frontend\XR_Vessel)
- `FoveAI\Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\README.md` _(spec)_ — Project README (FoveAI\Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master)
- `FoveAI\Frontend\multigate\README.md` _(spec)_ — Project README (FoveAI\Frontend\multigate)
- `FoveAI\Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-1\README.md` _(spec)_ — Project README (FoveAI\Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-1)
- `FoveAI\Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-2\README.md` _(spec)_ — Project README (FoveAI\Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\dataset\Bandai-Namco-Research-Motiondataset-2)
- `FoveAI\Frontend\XR_Vessel\public\README.md` _(spec)_ — Project README (FoveAI\Frontend\XR_Vessel\public)
- `FoveAI\Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\utils\blender\README.md` _(spec)_ — Project README (FoveAI\Frontend\XR_Vessel\public\Animations\BVH\Bandai-Namco-Research-Motiondataset-master\Bandai-Namco-Research-Motiondataset-master\utils\blender)
- `FoveAI\foveated-memory\README.md` _(spec)_ — Project README (FoveAI\foveated-memory)
- `FoveAI\Frontend\3D_Avatar_Chatbot\vrm-factory\README.md` _(spec)_ — Project README (FoveAI\Frontend\3D_Avatar_Chatbot\vrm-factory)
- `FoveAI\Frontend\3D_Avatar_Chatbot\vendor\animations\vrma\README.md` _(spec)_ — Project README (FoveAI\Frontend\3D_Avatar_Chatbot\vendor\animations\vrma)
- `FoveAI\Frontend\3D_Avatar_Chatbot\README.md` _(spec)_ — Project README (FoveAI\Frontend\3D_Avatar_Chatbot)
- `FoveAI\Frontend\3D_Avatar_Chatbot\nexus-proxy\README.md` _(spec)_ — Project README (FoveAI\Frontend\3D_Avatar_Chatbot\nexus-proxy)
- `FoveAI\Frontend\3D_Avatar_Chatbot\docs\README.md` _(spec)_ — Project README (FoveAI\Frontend\3D_Avatar_Chatbot\docs)
- `FoveAI\Frontend\3D_Avatar_Chatbot\addons\glb\README.md` _(spec)_ — Project README (FoveAI\Frontend\3D_Avatar_Chatbot\addons\glb)
- `FoveAI\Frontend\3D_Avatar_Chatbot\addons\vrma-actions\README.md` _(spec)_ — Project README (FoveAI\Frontend\3D_Avatar_Chatbot\addons\vrma-actions)
- `FoveAI\Frontend\3D_Avatar_Chatbot\addons\vrma-dance\README.md` _(spec)_ — Project README (FoveAI\Frontend\3D_Avatar_Chatbot\addons\vrma-dance)
- `FoveAI\Backend\preflight\README.md` _(spec)_ — Project README (FoveAI\Backend\preflight)
- `FoveAI\Backend\Cognition\README.md` _(spec)_ — Project README (FoveAI\Backend\Cognition)
- `FoveAI\.antigravityIDE\README.md` _(spec)_ — Project README (FoveAI\.antigravityIDE)
- `FoveAI\.ai\README.md` _(spec)_ — Project README (FoveAI\.ai)
- `FoveAI\ARCHITECTURE.md` _(spec)_ — Architecture spec (FoveAI)
- `FoveAI\.agents\ARCHITECTURE.md` _(spec)_ — Architecture spec (FoveAI\.agents)
- `FoveAI\Frontend\PLAN.md` _(spec)_ — Spec: FoveAI\Frontend\PLAN.md
- `FoveAI\Frontend\3D_Avatar_Chatbot\PLAN.md` _(spec)_ — Spec: FoveAI\Frontend\3D_Avatar_Chatbot\PLAN.md

## Skills
- **ENABLED** — changelog, nexysync-mcp, MCP Tool Orchestration Patterns, Zapier Workflows, Signs of AI Writing, 01-introductory, 02-elementary-rules-of-usage, 03-elementary-principles-of-composition, 04-a-few-matters-of-form, 05-words-and-expressions-commonly-misused, Research Poster Guidelines, Core DataFrames and Data Loading, Machine Learning, Performance and Optimization, Visualization & Simulation in PyLabRobot, Additional USPTO APIs Reference, PatentSearch API Reference, USPTO Trademark APIs Reference, Neon Developer Tools, Getting Started with Neon, Neon Auth, Neon and Drizzle Integration, Neon JS SDK, Neon Platform API, Neon Python SDK, Neon Serverless Driver, Neon TypeScript SDK, What is Neon, branches, PatentFig AI API — Endpoint Reference, guidelines, keys, organizations, Retrieve the first 10 projects, Neon Auth - Common Mistakes, Neon JS Data API Reference, Neon Auth - Auth Methods Reference, Neon Auth Setup - Next.js App Router, Neon Auth Setup - React SPA (Vite), Neon Auth - UI Components Reference, UniProt API Examples, UniProt API Fields Reference, UniProt ID Mapping Databases, UniProt Query Syntax Reference, TypeScript Cheatsheet, Goal Setting Frameworks for Treatment Plans, Evidence-Based Intervention Guidelines, Regulatory Compliance for Treatment Plans, Specialty-Specific Treatment Plan Guidelines, Treatment Plan Standards, Treatment Plan Quality Assurance Checklist, Professional Treatment Plan Styling - Quick Reference, Text Generation, PyHealth Models, Pipeline API Reference, PufferLib Training Guide, PyTorch Geometric Datasets Reference, PyTorch Geometric Neural Network Layers Reference, PyTorch Geometric Transforms Reference, Polars Core Concepts, Datasets, Models and Architectures, Molecular Generation, Molecular Property Prediction, Protein Modeling, Retrosynthesis, Pymoo Algorithms Reference, GPTQ Integration Guide, Tokenization Pipeline Components, Arctic Frost, Botanical Garden, Desert Rose, Forest Canopy, Golden Hour, Midnight Galaxy, Ocean Depths, Sunset Boulevard, Tech Innovation, Testing Anti-Patterns, Telegram Bot API - Complete Methods Reference, Telegram Bot API - Complete Types Reference, Telegram Bot - Implementation Patterns & Examples, Workflow Guide, Condition-Based Waiting, Defense-in-Depth Validation, Root Cause Tracing, Pressure Test 1: Emergency Production Fix, Pressure Test 2: Sunk Cost + Exhaustion, Pressure Test 3: Authority + Social Pressure, SymPy Advanced Topics, SymPy Core Capabilities, SymPy Matrices and Linear Algebra, SymPy Physics and Mechanics, approachable-concurrency, swift-6-2-concurrency, Artifact Reference, Command Reference, Repo Workflow Example, Research Workflow Example, Postgres Best Practices, Use tsvector for Full-Text Search, Index JSONB Columns for Efficient Querying, Configure Idle Connection Timeouts, Set Appropriate Connection Limits, Use Connection Pooling for All Applications, Use Prepared Statements Correctly with Pooling, Batch INSERT Statements for Bulk Data, Use Cursor-Based Pagination Instead of OFFSET, Use UPSERT for Insert-or-Update Operations, Use Advisory Locks for Application-Level Locking, Prevent Deadlocks with Consistent Lock Ordering, Use SKIP LOCKED for Non-Blocking Queue Processing, Maintain Table Statistics with VACUUM and ANALYZE, Create Composite Indexes for Multi-Column Queries, Use Covering Indexes to Avoid Table Lookups, Choose the Right Index Type for Your Data, Add Indexes on WHERE and JOIN Columns, Use Partial Indexes for Filtered Queries, Choose Appropriate Data Types, Index Foreign Key Columns, Use Lowercase Identifiers for Compatibility, Partition Large Tables for Better Performance, Select Optimal Primary Key Strategy, Apply Principle of Least Privilege, Enable Row Level Security for Multi-Tenant Data, Optimize RLS Policies for Performance, Writing Guidelines for Postgres Rules, Section Definitions, Clear, Action-Oriented Title (e.g., "Use Partial Indexes for Filtered Queries"), Code Quality Reviewer Prompt Template, Implementer Subagent Prompt Template, Spec Compliance Reviewer Prompt Template, STRING Database API Reference, Discrete Choice Models Reference, Generalized Linear Models (GLM) Reference, Linear Regression Models Reference, Statistical Tests and Diagnostics Reference, Time Series Analysis Reference, Statistical Assumptions and Diagnostic Procedures, Bayesian Statistical Analysis, Effect Sizes and Power Analysis, Scientific Reporting Standards and Guidelines, Statistical Test Selection Guide, Atlas Cloud speech backend, Audio Speech API quick reference, Instructioning best practices (TTS), Sample instruction templates (copy/paste), Voice directions, Post-hoc Analyzer Agent, Hook Mechanisms - Deep Dive, SimPy Events System, SimPy Monitoring and Data Collection, SimPy Process Interaction, SimPy Real-Time Simulations, Resource Management in PyLabRobot, SHAP Theoretical Foundation, Handoff Template, Resume Checklist, Agentic System Design, Llm Evaluation Frameworks, Prompt Engineering Patterns, Llm Integration Guide, Mlops Production Patterns, Rag System Architecture, Experiment Design Frameworks, Feature Engineering Patterns, Statistical Methods Advanced, Dataops Best Practices, Data Modeling Patterns, Data Pipeline Architecture, Computer Vision Architectures, Object Detection Optimization, Production Vision Systems, Application Security & Secure SDLC, Security Architecture & Design, Security Operations & Incident Response, Threat Modeling & Risk Assessment, Incident Response Report Template, Examples: Planning with Files in Action, Seaborn Function Reference, Seaborn Objects Interface, ATAC-seq and Chromatin Accessibility Models, Multimodal and Multi-omics Integration Models, Single-Cell RNA-seq Models, Spatial Transcriptomics Models, Specialized Modality Models, Theoretical Foundations of scvi-tools, Competing Risks Analysis, Cox Proportional Hazards Models, Data Handling and Preprocessing, Ensemble Models for Survival Analysis, Evaluation Metrics for Survival Models, Survival Support Vector Machines, Model Selection and Evaluation Reference, Pipelines and Composite Estimators Reference, Scikit-learn Quick Reference, Supervised Learning Reference, Unsupervised Learning Reference, Figures and Tables Best Practices, Scientific Writing Principles, Scientific Color Palettes and Guidelines, Publication-Ready Matplotlib Examples, Publication-Ready Figure Guidelines, Data Visualization for Slides, Presentation Structure Guide, Slide Design Principles for Scientific Presentations, Scientific Talk Types Guide, Visual Review Workflow for Presentations, Presentation Timing Guidelines, Scientific Schematics - Quick Reference, Polars Best Practices and Performance Guide, Evidence Hierarchy and Quality Assessment, Experimental Design Checklist, Logical Fallacies in Scientific Discourse, Scientific Method Core Principles, Common Statistical Pitfalls, Advanced Brainstorming Methodologies, ScholarEval Evaluation Framework, Scanpy Plotting Guide, Standard Scanpy Workflow for Single-Cell Analysis, Broader Impacts: Strategies and Best Practices, DARPA (Defense Advanced Research Projects Agency) Grant Writing Guidelines, NSF (National Science Foundation) Grant Writing Guidelines, NIH Specific Aims Page: The Complete Guide, Budget Justification Template, NIH Specific Aims Page Template, NSF Project Summary Template, Code Review Agent, Direct Creation (MCP) Details, Error patterns (compact), Render Service Types, 3d, assets, audio, calculate-metadata, can-decode, charts, compositions, display-captions, extract-frames, fonts, get-audio-duration, get-video-dimensions, get-video-duration, gif, images, import-srt-captions, lottie, measuring-dom-nodes, measuring-text, sequencing, tailwind, text-animations, timing, transcribe-captions, transitions, trimming, videos, EU MDR 2017/745 Submission Guide, Adding Reference Mindsets, Data-Oriented Design, Simplicity vs Easy, Better Alternatives to useEffect, useEffect Anti-Patterns, Event Handler TypeScript Patterns, Hook TypeScript Patterns, React 19 TypeScript Patterns, React Router v7 - Comprehensive Reference Guide, TanStack Router TypeScript Patterns, Generic Component Patterns, Store Event Handlers in Refs, Prevent Waterfall Chains in API Routes, Defer Await Until Needed, Dependency-Based Parallelization, Strategic Suspense Boundaries, Avoid Barrel File Imports, Conditional Module Loading, Defer Non-Critical Third-Party Libraries, Dynamic Imports for Heavy Components, Preload Based on User Intent, Deduplicate Global Event Listeners, Use SWR for Automatic Deduplication, Batch DOM CSS Changes, Cache Repeated Function Calls, Cache Property Access in Loops, Cache Storage API Calls, Combine Multiple Array Iterations, Early Return from Functions, Hoist RegExp Creation, Build Index Maps for Repeated Lookups, Early Length Check for Array Comparisons, Use Loop for Min/Max Instead of Sort, Use Set/Map for O(1) Lookups, Use toSorted() Instead of sort() for Immutability, Use Activity Component for Show/Hide, Animate SVG Wrapper Instead of SVG Element, Use Explicit Conditional Rendering, Hoist Static JSX Elements, Prevent Hydration Mismatch Without Flickering, Optimize SVG Precision, Defer State Reads to Usage Point, Subscribe to Derived State, Use Functional setState Updates, Extract to Memoized Components, Use Transitions for Non-Urgent Updates, Cross-Request LRU Caching, Per-Request Deduplication with React.cache(), Minimize Serialization at RSC Boundaries, RDKit Molecular Descriptors Reference, Common SMARTS Patterns for RDKit, AWQ Advanced Usage Guide, AWQ Troubleshooting Guide, FAISS Index Types Guide, Advanced Features, QuTiP Analysis and Measurement, QuTiP Time Evolution and Dynamics Solvers, Quantum Circuit Building, Bug Report Templates, Figma Design Validation with MCP, Test Case Templates, LightningDataModule - Comprehensive Guide, Distributed Training - Comprehensive Guide, LightningModule - Comprehensive Guide, Logging - Comprehensive Guide, Trainer - Comprehensive Guide, TDC Molecule Generation Oracles, TDC Utilities and Data Functions, Working with Sequence Files (FASTA/FASTQ), Core Data Structures, Feature Detection and Linking, Peptide and Protein Identification, Metabolomics Workflows, Signal Processing, Pymoo Constraints and Decision Making Reference, Pymoo Genetic Operators Reference, Pymoo Test Problems Reference, PyMC Distributions Reference, PyMC Sampling and Inference Methods, Pymatgen Analysis Modules Reference, Pymatgen Core Classes Reference, Materials Project API Reference, Analytical Equipment in PyLabRobot, Liquid Handling with PyLabRobot, Material Handling Equipment in PyLabRobot, PyHealth Medical Code Translation, PyHealth Clinical Prediction Tasks, PyHealth Training, Evaluation, and Interpretability, Common DICOM Tags Reference, PyDESeq2 Workflow Guide, PufferLib Environments Guide, PufferLib Policies Guide, PufferLib Vectorization Guide, Common OpenAlex Query Examples, PubMed Search Syntax and Field Tags, Protocols.io Authentication, Discussions API, File Manager API, Protocols API, Workspaces API, Chain-of-Thought Prompting, Prompt Optimization Guide, Prompt Template Systems, System Prompt Design, Prompt Template Library, Comprehensive JSON Generation Guide, Provider Configuration, Advanced Validation Patterns, Comprehensive Constraint Patterns, DSPy Modules, DSPy Optimizers (Teleprompters), Email Templates for Developers, Technical Jargon Simplification Guide, Remote and Async Communication, Research Poster Design Principles, Poster Layout and Design Guide, Research Poster Quality Checklist, Editing Presentations, PptxGenJS Tutorial, HTML to PowerPoint Guide, miles API Reference, DPO Variants, Online RL Methods, Reward Modeling, SFT Training Guide, Hyperparameters, Loss Functions, Algorithm Comparison, Custom Reward Functions, Hybrid Engine Architecture, Multi-Node Training, Pandas to Polars Migration Guide, Component Organization Patterns, Plugin Manifest Reference, Advanced Plugin Example, Minimal Plugin Example, Settings File Parsing Techniques, Real-World Plugin Settings Examples, Create Plugin Settings, Example Plugin Settings File, Marketplace Schema Reference, Plotly Chart Types, Export and Interactivity, Graph Objects - Low-Level API, Layouts, Styling, and Customization, Plotly Express - High-Level API, Playwright Java – Assertions Reference, Playwright Java – Project Configuration, Playwright Java – Fixtures, Hooks & Test Data, Playwright Java – Page Object Patterns, Findings & Decisions, Progress Log, Task Plan: [Brief Description], Perplexity Model Comparison, OpenRouter Setup Guide, Search Strategies for Perplexity, Advanced Features in PennyLane, Devices and Backends in PennyLane, Getting Started with PennyLane, Optimization in PennyLane, Quantum Chemistry with PennyLane, Quantum Circuits in PennyLane, Quantum Machine Learning with PennyLane, Common Methodological and Statistical Issues in Scientific Manuscripts, Fillable fields, PDF OCR Processing Guide, PDF Table Extraction Guide, Fillable fields, Data Management & Storage, Graph Construction & Spatial Analysis, Multiparametric Imaging, Paper2Poster: Academic Poster Generation, Paper2Video: Presentation Video Generation, Paper2Web: Academic Homepage Generation, Usage Examples and Workflows, GPTQ Calibration Guide, Performance Benchmarks, HuggingFace Transformers Integration, Memory Optimization, QLoRA Training, Evidence Types and Data Sources, Target Annotations and Features, OpenAlex API Complete Guide, Connection & Session Management, Data Access & Retrieval, Image Processing & Rendering, Metadata & Annotations, Regions of Interest (ROIs), Scripts & Batch Operations, OMERO Tables
- **ASK** — imprint, imprint, imprint, imprint, omero-integration, Open Targets Platform API Reference, Skill authoring best practices, Persuasion Principles for Skill Design, Testing Skills With Subagents, Testing CLAUDE.md Skills Documentation, OpenAPI to TypeScript, Conference Formatting Requirements, Grant Proposal Requirements, Journal Formatting Requirements, Data Processing and Manipulation, I/O Operations, Patent Examination Data System (PEDS) API Reference, Connection Methods, Neon Features, Neon CLI, Referencing Neon Docs, Polars Operations Reference, Tokenizers, gpt-4o-transcribe-diarize quick reference, Knowledge Graph Reasoning, Modern Minimalist, Task Format Specification, Creation Log: Systematic Debugging Skill, Academic Test: Systematic Debugging Skill, SymPy Code Generation and Printing, SwiftUI Concurrency Tour (Summary), Troubleshooting - Skill Activation Issues, Smoke Prompts, Quickstart Example, Eliminate N+1 Queries with Batch Loading, Keep Transactions Short to Reduce Lock Contention, Use EXPLAIN ANALYZE to Diagnose Slow Queries, Enable pg_stat_statements for Query Analysis, Callbacks - Comprehensive Guide, Creating Custom Environments for Stable Baselines3, Vectorized Environments in Stable Baselines3, Accessibility read defaults, Playwright CLI Reference, Codex network approvals / sandbox notes, IVR / phone prompt defaults, Narration / explainer defaults, Product demo / voiceover defaults, JSON Schemas, skill-creator, Blind Comparator Agent, Grader Agent, Advanced Topics & Future Enhancements, Common Patterns Library, skill-rules.json - Complete Reference, Trigger Types - Complete Guide, Output Patterns, Playwright CLI Workflows, SHAP Explainers Reference, SHAP Visualization Reference, Model-Specific Expectations, Test Results: Opus 4.5 (Baseline), Evaluation Test Scenarios, Cryptography Implementation, Penetration Testing Guide, Security Architecture Patterns, Compliance Requirements, Security Standards, Vulnerability Management Guide, Qa Best Practices, Testing Strategies, Test Automation Patterns, Architecture Patterns, Development Workflows, Tech Stack Guide, Frontend Best Practices, Nextjs Optimization Guide, React Patterns, Cicd Pipeline Guide, Deployment Strategies, Infrastructure As Code, Api Design Patterns, Backend Security Practices, Database Optimization Guide, System Design Workflows, Tech Decision Guide, Compliance Frameworks, SOC 2 Control Documentation Example, Differential Expression Analysis in scvi-tools, Output Format Reference, Preprocessing Pipelines & Transforms, Citation Styles Guide, IMRAD Structure Guide, Reporting Guidelines for Scientific Studies, Journal-Specific Figure Requirements, LaTeX Beamer Guide for Scientific Presentations, PowerPoint Design Guide for Scientific Presentations, Common Biases in Scientific Research, DOE (Department of Energy) Grant Writing Guidelines, NIH (National Institutes of Health) Grant Writing Guidelines, Render Blueprint Specification, Codebase Analysis (Deploy), Render Configuration Guide, Deployment Details, Post-deploy checks, Render Runtime Options, Basic troubleshooting (deploy-time and startup), animations, FDA Submission Guide, Composition Over Construction, PAGNI: Probably Are Gonna Need It, Server Components and Server Actions, useLatest for Stable Callback Refs, Promise.all() for Independent Operations, CSS content-visibility for Long Lists, Narrow Effect Dependencies, Use Lazy State Initialization, Use after() for Non-Blocking Operations, Parallel Data Fetching with Component Composition, Pinecone Deployment Guide, Backend Configuration Guide, Qiskit Patterns: The Four-Step Workflow, Qiskit Primitives, Qiskit Setup and Installation, Circuit Transpilation and Optimization, Regression Testing Guide, Python Testing Patterns Implementation Playbook, Working with Alignment Files (SAM/BAM/CRAM), Common Bioinformatics Workflows with Pysam, Working with Variant Files (VCF/BCF), File I/O and Data Formats, Pymatgen I/O and File Format Reference, Pymatgen Transformations and Common Workflows, Hardware Backends in PyLabRobot, DICOM Transfer Syntaxes Reference, Additional Features, Few-Shot Learning Guide, Meeting Structures for Developers, Research Poster Content Guide, Office Open XML Technical Reference for PowerPoint, postgres-schema-design, Polars Data I/O Guide, Polars Data Transformations, Standard Plugin Example, Plugin Structure Reference, Playwright Skill - Complete API Reference, PDF Processing Advanced Reference, Image Loading & Formats, Installation and Configuration, Quantization Formats

## Skill instructions (excerpts)
_The full content lives at the path shown. Read the source file before invoking._

### changelog _(ENABLED)_
Source: `FoveAI\client_quest\Library\PackageCache\com.unity.timeline@8cd8509afae5\.claude\skills\changelog\SKILL.md`

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
> Search tools will NOT find it. To

…_(truncated)_

### MCP Tool Orchestration Patterns _(ENABLED)_
Source: `..\..\.gemini\skills\zapier-workflows\references\mcp-patterns.md`

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
Source: `..\..\.gemini\skills\zapier-workflows\references\zaps.md`

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
Source: `..\..\.gemini\skills\writing-clearly-and-concisely\signs-of-ai-writing.md`

# Signs of AI Writing

[![A screenshot of ChatGPT reading: "[header] Legacy & Interpretation [body] The "Black Hole Edition" is not just a meme — it's a celebration of grassroots car culture, where ideas are limitless and fun is more important than spec sheets. Whether powered by a rotary engine, a V8 swap, or an imagined fighter jet turbine, the Miata remains the canvas for car enthusiasts

…_(truncated)_

### 01-introductory _(ENABLED)_
Source: `..\..\.gemini\skills\writing-clearly-and-concisely\elements-of-style\01-introductory.md`

## I. Introductory

This handbook summarizes the essentials of plain English style. It focuses on the rules of usage and principles of composition most often broken, offering a compact alternative to exhaustive manuals. Master the guidance here, then look to the best authors for finer points of style.

### 02-elementary-rules-of-usage _(ENABLED)_
Source: `..\..\.gemini\skills\writing-clearly-and-concisely\elements-of-style\02-elementary-rules-of-usage.md`

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
Source: `..\..\.gemini\skills\writing-clearly-and-concisely\elements-of-style\03-elementary-principles-of-composition.md`

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
