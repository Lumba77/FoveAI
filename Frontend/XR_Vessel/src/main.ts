import * as THREE from 'three';
import { HTMLMesh } from 'three/examples/jsm/interactive/HTMLMesh.js';
import { InteractiveGroup } from 'three/examples/jsm/interactive/InteractiveGroup.js';
import * as ThreeMeshUI from 'three-mesh-ui';
(window as any).THREE = THREE;

// Browser Cleanse Resilience: Memory auto-restore + periodic backup
import './memoryBridge';

// Director Voice Engine — spooky pitch-down narrator + Avalanche dark ambient music
import { directorVoice } from './senses/DirectorVoiceEngine';

// Code Agency: Frontend client for /api/code/* endpoints
import { CodeAgency } from './agency/CodeAgency';

// "Tap to Start" overlay — required for speech synthesis permission on WebXR
// Browsers block speechSynthesis.speak() until user gesture
let _userHasInteracted = false;
(window as any).foveaiUserInteracted = false;
const _unlockInteraction = async () => {
    if (_userHasInteracted) return;
    _userHasInteracted = true;
    (window as any).foveaiUserInteracted = true;
    const overlay = document.getElementById('foveai-tap-overlay');
    // Warm up speech synthesis engine
    try { speechSynthesis.speak(new SpeechSynthesisUtterance('')); speechSynthesis.cancel(); } catch { }

    // Warm up AudioContext directly on the user gesture to prevent autoplay suspension
    const AudioContextClass = (window as any).AudioContext || (window as any).webkitAudioContext;
    if (AudioContextClass && !(window as any).foveaiAudioContext) {
        (window as any).foveaiAudioContext = new AudioContextClass();
    }
    if ((window as any).foveaiAudioContext && (window as any).foveaiAudioContext.state === 'suspended') {
        (window as any).foveaiAudioContext.resume().catch((e: any) => console.warn('AudioContext resume failed:', e));
    }

    // Auto-enter XR in Quest mode
    if (contextManager.getUnit() === 'qu' || contextManager.getUnit() === 'q3') {
        if (!cachedMicStream) {
            (window as any).log?.('[Quest Mode] Requesting Microphone Permission first...', '#00f3ff');
            const overlayText = document.querySelector('#start-overlay span');
            if (overlayText) overlayText.textContent = "Waiting for Microphone Permission...";

            try {
                cachedMicStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
                (window as any).foveaiCachedMicStream = cachedMicStream;
                if (overlayText) overlayText.textContent = "Microphone Granted! Click again to Enter AR.";
            } catch (e: any) {
                if (overlayText) overlayText.textContent = "Mic Denied. Click again to enter AR anyway.";
                cachedMicStream = "denied" as any; // Mark as processed
            }
            _userHasInteracted = false;
            return; // Stop here and wait for the second click to actually start XR!
        }

        if (overlay) overlay.remove();
        document.removeEventListener('click', _unlockInteraction);
        document.removeEventListener('touchstart', _unlockInteraction);
        document.removeEventListener('keydown', _unlockInteraction);

        (window as any).log?.('[Quest Mode] Tap detected. Requesting WebXR Immersive Session...', '#00f3ff');
        if (env) {
            env.renderer.domElement.style.display = 'block';
        }
        // Default to AR (Passthrough) so the background is transparent!
        const targetMode: 'ar' | 'vr' = 'ar';
        startXRSession(targetMode);
    } else {
        if (overlay) overlay.remove();
        document.removeEventListener('click', _unlockInteraction);
        document.removeEventListener('touchstart', _unlockInteraction);
        document.removeEventListener('keydown', _unlockInteraction);
    }
};
document.addEventListener('click', _unlockInteraction, { once: false });
document.addEventListener('touchstart', _unlockInteraction, { once: false });
document.addEventListener('keydown', _unlockInteraction, { once: false });

// Pin preferred voice: young female, not the default "old nagging witch"
const _PREFERRED_VOICE_NAMES = ['Google UK English Female', 'Microsoft Zira', 'Samantha', 'Karen', 'Veena', 'Google US English', 'Female'];
function _pinBestVoice() {
    const voices = speechSynthesis.getVoices();
    if (!voices.length) return;
    const saved = localStorage.getItem('foveai_preferred_voice');
    if (saved) {
        const found = voices.find(v => v.name === saved);
        if (found) { (window as any).foveaiPreferredVoice = found; return; }
    }
    for (const pref of _PREFERRED_VOICE_NAMES) {
        const match = voices.find(v => v.name.includes(pref));
        if (match) {
            (window as any).foveaiPreferredVoice = match;
            localStorage.setItem('foveai_preferred_voice', match.name);
            return;
        }
    }
    // Fallback: pick any English female voice
    const enFemale = voices.find(v => v.lang.startsWith('en') && v.name.toLowerCase().includes('female'));
    if (enFemale) {
        (window as any).foveaiPreferredVoice = enFemale;
        localStorage.setItem('foveai_preferred_voice', enFemale.name);
    }
}
if (typeof speechSynthesis !== 'undefined') {
    speechSynthesis.onvoiceschanged = _pinBestVoice;
    _pinBestVoice(); // Try immediately too
}

// GLOBAL VERSIONING & BOOT TRACKING
(window as any).LINK_REVISION = "OMEGA_511";

(window as any).log?.(`LINK_REVISION: ${(window as any).LINK_REVISION}`, '#39ff14');
(window as any).log?.('Omega Link: Stabilizing Core...');
(window as any).log?.('Vessel: Requesting Avatar from /avatars/', '#00f3ff');

if (typeof (window as any).foveaiBootCount === 'undefined') {
    (window as any).foveaiBootCount = 0;
}

import { Environment } from './scene/Environment';
import { AvatarManager } from './avatar/AvatarManager';
import { SoftLayerLoader } from './softlayer/SoftLayerLoader';
import { localMemory } from './network/LocalMemory';
import { localArtillery } from './network/LocalArtillery';
import { AuralAwareness } from './senses/AuralAwareness';
import { RoomSpatialContext } from './senses/RoomSpatialContext';
import { SpatialEnvironment } from './senses/SpatialEnvironment';
import { RoomScanner } from './senses/RoomScanner';
import { soundboardRegistry } from './senses/SoundboardRegistry';
import { initVisionSystem, enableAvatarVisionLayers, captureVisionForLLM, getCompositeVision } from './senses/VisionIntegration';
import { Dashboard } from './components/Dashboard';
import { HapticWand } from './avatar/HapticWand';
import { VideoChat } from './components/VideoChat';
import { impulseManager } from './network/ImpulseManager';
import { contextManager } from './ContextManager';
import { XrIdeHud, type DevEditsPayload } from './ui/XrIdeHud';
// Force immediate version buster check to reload if url param v is outdated!
contextManager.checkVersionBuster();

import { XRControllerModelFactory } from 'three/examples/jsm/webxr/XRControllerModelFactory.js';
import { BracketParser } from './senses/BracketParser';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import html2canvas from 'html2canvas';

// Set default mode to AR for XR/Vessel - VR is fallback, desktop is fallback for fallback
(window as any).foveaiDefaultXrMode = 'ar'; // Default to AR/XR

// DEFENSIVE CHECK: Wait for XR system to be available before starting
async function waitForXRSystem(): Promise<boolean> {
    if (!navigator.xr) {
        (window as any).log?.('XR system not available', '#ffaa00');
        return false;
    }

    try {
        const available = await navigator.xr.isSessionSupported('immersive-ar') ||
            await navigator.xr.isSessionSupported('immersive-vr');
        return available;
    } catch (e) {
        (window as any).log?.('XR system check failed', '#ffaa00');
        return false;
    }
}

// Prevent errors when XR session starts too early
let xrSessionPending = false;

// Optimization: Conditional Initialization based on Mode (OMEGA_085)
const shouldInit3D = contextManager.shouldInit3D();

const env = shouldInit3D ? new Environment() : null;
if ((contextManager.getUnit() === 'qu' || contextManager.getUnit() === 'q3') && env) {
    env.renderer.domElement.style.display = 'none';
}
const avatar = shouldInit3D ? new AvatarManager() : null;
const agyAvatar = shouldInit3D ? new AvatarManager() : null;
if (agyAvatar) (window as any).agyAvatar = agyAvatar;

// ── SoftLayer: hot-reloadable JS modules for environment/behavior control ──
// Fetches configs and modules from the XRLF API and executes them in a
// sandboxed FoveAI context. This enables changing lighting, particles,
// clothing, sky, avatar behavior, etc. without rebuilding the APK.
const softLayer = new SoftLayerLoader('http://127.0.0.1:8402');
(window as any).foveaiSoftLayer = softLayer;
if (shouldInit3D) {
    softLayer.init().then(() => {
        softLayer.startUpdateLoop();

        // ── Apply webcam plaster SoftLayer params ──
        // Listen for changes to webcamPlaster.* params and apply them to SpatialEnvironment
        const applyWebcamPlasterParams = () => {
            const se = (window as any).spatialEnvironment;
            if (!se) return;
            const params = (window as any).FoveAIParams || {};
            if ('webcamPlaster.enabled' in params) se.setWebcamPlasterEnabled(params['webcamPlaster.enabled']);
            if ('webcamPlaster.opacity' in params) se.setWebcamPlasterOpacity(params['webcamPlaster.opacity']);
            if ('webcamPlaster.orientation' in params) se.setWebcamOrientation(params['webcamPlaster.orientation']);
        };
        // Apply once on init
        setTimeout(applyWebcamPlasterParams, 2000);
        // Listen for future changes
        if (!(window as any).FoveAIParamsListeners) (window as any).FoveAIParamsListeners = {};
        const listeners = (window as any).FoveAIParamsListeners;
        for (const key of ['webcamPlaster.enabled', 'webcamPlaster.opacity', 'webcamPlaster.orientation']) {
            if (!listeners[key]) listeners[key] = [];
            listeners[key].push(applyWebcamPlasterParams);
        }

        // ── Apply "Be Jen" POV SoftLayer param ──
        const applyJenPovParam = () => {
            const params = (window as any).FoveAIParams || {};
            if ('avatar.jenPOV' in params) {
                (window as any).foveaiSetJenPov?.(params['avatar.jenPOV']);
            }
        };
        setTimeout(applyJenPovParam, 2000);
        if (!listeners['avatar.jenPOV']) listeners['avatar.jenPOV'] = [];
        listeners['avatar.jenPOV'].push(applyJenPovParam);

        // ── Apply Director voice & Avalanche music SoftLayer params ──
        const applyDirectorParams = () => {
            const params = (window as any).FoveAIParams || {};
            const dv = (window as any).foveaiDirectorVoice;
            if (!dv) return;
            if ('director.voicePitch' in params) dv.setVoicePitch(params['director.voicePitch']);
            if ('director.voiceRate' in params) dv.setVoiceRate(params['director.voiceRate']);
            if ('director.voiceVolume' in params) dv.setVoiceVolume(params['director.voiceVolume']);
            if ('director.reverbAmount' in params) dv.setReverbAmount(params['director.reverbAmount']);
            if ('director.filterCutoff' in params) dv.setFilterCutoff(params['director.filterCutoff']);
            if ('director.avalancheVolume' in params) dv.setMusicVolume(params['director.avalancheVolume']);
            if ('director.avalancheMusic' in params) {
                const shouldPlay = params['director.avalancheMusic'];
                if (shouldPlay && !dv.isMusicPlaying) dv.startAvalancheMusic();
                else if (!shouldPlay && dv.isMusicPlaying) dv.stopAvalancheMusic();
            }
            if ('director.radioEffect' in params) dv.setRadioEffect(params['director.radioEffect']);
            if ('director.radioIntensity' in params) dv.setRadioIntensity(params['director.radioIntensity']);
        };
        setTimeout(applyDirectorParams, 2000);
        for (const key of ['director.voicePitch', 'director.voiceRate', 'director.voiceVolume',
                           'director.reverbAmount', 'director.filterCutoff',
                           'director.avalancheMusic', 'director.avalancheVolume',
                           'director.radioEffect', 'director.radioIntensity']) {
            if (!listeners[key]) listeners[key] = [];
            listeners[key].push(applyDirectorParams);
        }
    }).catch((e) => {
        console.warn('[SoftLayer] Init failed (runtime may not be running):', e);
    });
}
const audio = new AuralAwareness();
(window as any).foveaiAudio = audio;
const spatial = new RoomSpatialContext();
const dashboard = new Dashboard();
(window as any).dashboard = dashboard;
(window as any).toggleHolographicPanel = toggleHolographicPanel;
const videoChat = new VideoChat();

// Instantiate and expose SpatialEnvironment and RoomScanner
const spatialEnv = shouldInit3D ? new SpatialEnvironment((msg, color) => dashboard.log(msg, color)) : null;
if (spatialEnv) {
    (window as any).spatialEnvironment = spatialEnv;
}
const roomScanner = shouldInit3D ? new RoomScanner((msg, color) => dashboard.log(msg, color)) : null;
if (roomScanner) {
    (window as any).roomScanner = roomScanner;
    const isScannerEnabled = localStorage.getItem('foveai_room_scanner_enabled') !== 'false';
    if (isScannerEnabled) {
        roomScanner.start();
    } else {
        dashboard.log('📷 Room Scanner auto-start disabled by setting', 'var(--neon-blue)');
    }
}

// Safe helper to trigger haptic feedback on Quest Browser (using .pulse) and PCVR (using .playEffect)
function triggerHaptic(gamepadOrSource: any, value: number, duration: number) {
    if (!gamepadOrSource) return;
    try {
        const gp = gamepadOrSource.gamepad ? gamepadOrSource.gamepad : gamepadOrSource;
        const actuator = gp?.hapticActuators?.[0] || gp?.vibrationActuator;
        if (!actuator) return;

        if (typeof actuator.pulse === 'function') {
            actuator.pulse(value, duration);
        } else if (typeof actuator.playEffect === 'function') {
            actuator.playEffect('dual-rumble', {
                startDelay: 0,
                duration: duration,
                weakMagnitude: value,
                strongMagnitude: value
            }).catch(() => { });
        }
    } catch (e) {
        console.warn('[XR] Haptic feedback failed:', e);
    }
}

// --- CONTROLLER STATE (declared before use to avoid TDZ) ---
let lastMenuButtonState = false;
let lastLeftMetaButtonState = false;
let lastRightMetaButtonState = false;
let lastGripChordState = false;
let lastTriggerChordState = false;
let lastTriggerState = [false, false];
let lastThumbstickClickState = [false, false];
let lastABState = [false, false];
let lastBYState = [false, false];
let thumbstickDeadzone = 0.15;
let movementSpeed = 1.5;
let rotationSpeed = 2.0;
let isTeleporting = false;
let isCrouching = false;
let hapticsWandMode = false;
let wandLeft: HapticWand | null = null;
let wandRight: HapticWand | null = null;
let leftThumbstickForward = false;
let teleportMarker: THREE.Mesh | null = null;
let leftGrip = false;
let rightGrip = false;
let leftTrigger = false;
let rightTrigger = false;
let leftThumbstickX = 0;
let leftThumbstickY = 0;
let laserPointerActive = false;
(window as any).doubleGripSteering = localStorage.getItem('foveai_double_grip_steering') !== 'false';
(window as any).doubleTriggerHaptics = localStorage.getItem('foveai_double_trigger_haptics') !== 'false';
let laserBeam: THREE.Line | null = null;
let laserBeamRight: THREE.Line | null = null;
let holographicCursorMesh: THREE.Mesh | null = null;
let holographicCursorRight: THREE.Mesh | null = null;
let holographicInputText = '';
let showVirtualKeyboard = false;
let rightBHeld = false;
let userWantsVad = false;
let thumbstickClickPending = [false, false];
let thumbstickClickTimer = [0, 0];
const THUMBSTICK_DOUBLE_THRESHOLD = 300;

const isHTMLMeshPixelTransparent = (hit: THREE.Intersection): boolean => {
    const mesh = hit.object as THREE.Mesh;
    if (!mesh || !mesh.material) return false;
    const mat = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
    const map = (mat as any).map as THREE.CanvasTexture;
    if (!map || !map.image) return false;
    const canvas = map.image as HTMLCanvasElement;
    const uv = hit.uv;
    if (!uv) return false;
    const x = Math.floor(uv.x * canvas.width);
    const y = Math.floor((1 - uv.y) * canvas.height);
    try {
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) return false;
        const pixel = ctx.getImageData(x, y, 1, 1).data;
        return pixel[3] < 15; // Treat alpha < 15 as transparent
    } catch (_e) {
        return false;
    }
};
let cachedMicStream: MediaStream | null = null;

// --- USER VR AVATAR GLOBALS & REPRESENTATION ---
let userAvatarGroup: THREE.Group | null = null;
let userHead: THREE.Mesh | null = null;
let userTorso: THREE.Mesh | null = null;
let userLeftHand: THREE.Mesh | null = null;
let userRightHand: THREE.Mesh | null = null;

// --- SPATIAL MIRROR PORTAL GLOBALS ---
let spatialPortalMesh: THREE.Mesh | null = null;
let spatialPortalBorder: THREE.Mesh | null = null;
let spatialPortalMaterial: THREE.MeshBasicMaterial | null = null;
let spatialPortalBorderMaterial: THREE.MeshStandardMaterial | null = null;
let mirrorVADDot: THREE.Mesh | null = null;
let mirrorVADIndicator: THREE.Mesh | null = null;

// --- 3D HOLOGRAPHIC MENU GLOBALS ---
let holographicPanelMesh: THREE.Mesh | null = null;
let holographicPanelCanvas: HTMLCanvasElement | null = null;
let holographicPanelTexture: THREE.CanvasTexture | null = null;
let lastChatHistoryLength = 0;
let lastListeningState = false;
let activeHolographicTab = 'cognition';
const holographicTabs = ['cognition', 'telemetry', 'swarm', 'features'];
let lastLeftThumbstickFlick = false;
let lastHudUpdateTime = 0;
let lastScanCaptureTime = 0;
let lastPlaneParseTime = 0;
let lastHolographicRenderId = 0;
let isHolographicRenderPending = false;
let holographicRedrawRequested = false;
let isDraggingMenu = false;
let draggingHand: 'left' | 'right' | null = null;
let originalParent: THREE.Object3D | null = null;
// Content hash cache: only call ThreeMeshUI.Text.set() when content actually changes
const _lastHolographicContent: Record<string, string> = {};
let isDevModeActive = false; // Dev Mode Active state tracking variable (globalized)
(window as any).isDevModeActive = false;
let isBrainThinking = false;
let lastBrainQueryStartTime = 0;
let lastDevFeedFetchTime = 0;
let holographicChatText: any = null;
let holographicIdentityText: any = null;
let holographicVadText: any = null;
let holographicThinkingText: any = null;
let holographicDevFeedText: any = null;
let xrIdeHud: XrIdeHud | null = null;
let lastXrIdeHudToggle = 0;
let lastDevEditsPoll = 0;

// --- DEV MODE TOGGLE ---
// Called by clicking DEV SYSTEM: OFFLINE/ACTIVE in the XRideHud indicator hub
// or by clicking the ph-dev peripheral icon.
function toggleDevMode() {
    isDevModeActive = !isDevModeActive;
    (window as any).isDevModeActive = isDevModeActive;

    // Refresh all HUD surfaces
    updateXRIndicatorHub();
    updatePeripheralHUD();

    // Toggle 3D XR-IDE HUD panel visibility based on dev mode state
    if (xrIdeHud) {
        xrIdeHud.setVisible(isDevModeActive);
    }

    // Log confirmation to dashboard
    const statusLabel = isDevModeActive ? 'ACTIVE (CODER)' : 'OFFLINE';
    if ((window as any).dashboard?.log) {
        const color = isDevModeActive ? 'var(--neon-cyan)' : 'var(--neon-pink)';
        (window as any).dashboard.log(`[XRideHud] DEV SYSTEM: ${statusLabel}`, color);
    }

    // Flash the devmode HUD panel for tactile feedback
    const devEl = document.getElementById('xr-hud-devmode');
    if (devEl) {
        devEl.style.transition = 'opacity 0.1s';
        devEl.style.opacity = '0.3';
        setTimeout(() => { devEl.style.opacity = '1'; }, 120);
    }

    // Dispatch custom event so other subsystems (XrIdeHud, compagent bridge) can react
    window.dispatchEvent(new CustomEvent('foveai-devmode-toggled', {
        detail: { active: isDevModeActive }
    }));

    // Force HTMLMesh texture refresh so the 3D object updates immediately
    if ((window as any).xr3dHudMesh) {
        try { ((window as any).xr3dHudMesh.material as any).map.update(); } catch (_e) { }
    }
    if ((window as any).xrPeripheralHudMesh) {
        try { ((window as any).xrPeripheralHudMesh.material as any).map.update(); } catch (_e) { }
    }
}
(window as any).toggleDevMode = toggleDevMode;


function initUserAvatar() {
    if (!env) return;

    userAvatarGroup = new THREE.Group();

    // Visor Head
    const headGeo = new THREE.TorusGeometry(0.12, 0.03, 8, 24);
    const headMat = new THREE.MeshBasicMaterial({
        color: 0x00f3ff,
        wireframe: true,
        transparent: true,
        opacity: 0.8
    });
    userHead = new THREE.Mesh(headGeo, headMat);
    userHead.rotation.x = Math.PI / 2; // Visor orientation
    userAvatarGroup.add(userHead);

    // Torso
    const torsoGeo = new THREE.CylinderGeometry(0.18, 0.22, 1.0, 8, 1, true);
    const torsoMat = new THREE.MeshBasicMaterial({
        color: 0x00f3ff,
        wireframe: true,
        transparent: true,
        opacity: 0.35
    });
    userTorso = new THREE.Mesh(torsoGeo, torsoMat);
    userAvatarGroup.add(userTorso);

    // Left Hand (Cyan)
    const handGeo = new THREE.SphereGeometry(0.04, 8, 8);
    const leftHandMat = new THREE.MeshBasicMaterial({
        color: 0x00f3ff,
        wireframe: true,
        transparent: true,
        opacity: 0.7
    });
    userLeftHand = new THREE.Mesh(handGeo, leftHandMat);
    userAvatarGroup.add(userLeftHand);

    // Right Hand (Pink)
    const rightHandMat = new THREE.MeshBasicMaterial({
        color: 0xff0088,
        wireframe: true,
        transparent: true,
        opacity: 0.7
    });
    userRightHand = new THREE.Mesh(handGeo, rightHandMat);
    userAvatarGroup.add(userRightHand);

    // Crucial: Put the entire virtual user representation on Layer 1!
    // This makes it visible to Jen's head camera (which enables Layer 1) but
    // invisible to the user's own eyes (which only renders Layer 0), preventing clipping!
    userAvatarGroup.traverse((child) => {
        child.layers.set(1);
    });

    env.scene.add(userAvatarGroup);
    console.log('[XR] User Virtual representation initialized on Layer 1');

    // Create the Holographic Mirror Portal in the room corner (Layer 0, so visible to both User and Jen)
    const portalGeo = new THREE.PlaneGeometry(1.6, 0.9);
    spatialPortalMaterial = new THREE.MeshBasicMaterial({
        color: 0x05080c,
        side: THREE.DoubleSide
    });
    spatialPortalMesh = new THREE.Mesh(portalGeo, spatialPortalMaterial);

    // Position it in the room corner (2.2m right, 1.3m high, 1.8m back)
    spatialPortalMesh.position.set(2.2, 1.3, -1.8);
    // Angle it to face directly at the center of the room (where user & avatar stand)
    spatialPortalMesh.lookAt(0, 0.8, 0);
    spatialPortalMesh.name = 'spatial_portal';

    // Create a pulsing neon-cyan border frame surrounding the portal mirror
    const borderGeo = new THREE.BoxGeometry(1.64, 0.94, 0.02);
    spatialPortalBorderMaterial = new THREE.MeshStandardMaterial({
        color: 0x00f3ff,
        emissive: 0x00f3ff,
        emissiveIntensity: 1.5,
        wireframe: true,
        transparent: true,
        opacity: 0.8
    });
    spatialPortalBorder = new THREE.Mesh(borderGeo, spatialPortalBorderMaterial);
    spatialPortalBorder.position.copy(spatialPortalMesh.position);
    spatialPortalBorder.quaternion.copy(spatialPortalMesh.quaternion);
    spatialPortalBorder.name = 'spatial_portal_border';

    env.scene.add(spatialPortalMesh);
    env.scene.add(spatialPortalBorder);

    // Hide the portal meshes to keep the 3D scene clean, while keeping background video active
    spatialPortalMesh.visible = false;
    spatialPortalBorder.visible = false;

    // Initialize holographic VAD indicator on the mirror portal
    initMirrorVADIndicator();

    // Initialize 3D holographic menu overlay panel
    initHolographicPanel();

    // Request Direct Browser Camera stream for the portal!
    (async () => {
        try {
            let stream = (window as any).foveaiPortalStream as MediaStream | null;
            if (!stream && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                dashboard.log('[XR] Spatial Portal: Requesting camera stream...', 'var(--neon-blue)');

                // 1. Initial request to trigger browser permission prompt
                stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 360 } });

                // 2. Once permission is active, check the default device track label
                const defaultTrack = stream.getVideoTracks()[0];
                const defaultLabel = defaultTrack ? defaultTrack.label.toLowerCase() : '';

                const isVirtual = defaultLabel.includes('virtual') ||
                    defaultLabel.includes('obs') ||
                    defaultLabel.includes('oculus') ||
                    defaultLabel.includes('look') ||
                    defaultLabel.includes('avatar') ||
                    defaultLabel.includes('nvidia');

                if (isVirtual) {
                    dashboard.log(`[XR] Spatial Portal: Default camera "${defaultTrack.label}" appears virtual. Searching for physical camera...`, '#ffaa00');
                    try {
                        const devices = await navigator.mediaDevices.enumerateDevices();
                        const videoDevices = devices.filter(d => d.kind === 'videoinput');
                        const realDevices = videoDevices.filter(d => {
                            const lbl = d.label.toLowerCase();
                            return !lbl.includes('virtual') &&
                                !lbl.includes('obs') &&
                                !lbl.includes('oculus') &&
                                !lbl.includes('look') &&
                                !lbl.includes('avatar') &&
                                !lbl.includes('nvidia');
                        });

                        if (realDevices.length > 0 && realDevices[0].deviceId) {
                            dashboard.log(`[XR] Spatial Portal: Switching to physical camera "${realDevices[0].label}"`, 'var(--neon-blue)');
                            // Stop initial temporary stream
                            stream.getTracks().forEach(t => t.stop());
                            // Request specific physical device
                            stream = await navigator.mediaDevices.getUserMedia({
                                video: { deviceId: { exact: realDevices[0].deviceId }, width: 640, height: 360 }
                            });
                        }
                    } catch (enumErr) {
                        console.warn('[Portal] Failed to switch camera device:', enumErr);
                    }
                } else {
                    dashboard.log(`[XR] Spatial Portal: Using default physical camera "${defaultTrack ? defaultTrack.label : 'Default'}"`, '#39ff14');
                }

                (window as any).foveaiPortalStream = stream;
            }

            if (stream) {
                const videoEl = (window as any).foveaiPortalVideo || document.createElement('video');
                if (!videoEl.srcObject) {
                    videoEl.srcObject = stream;
                    videoEl.autoplay = true;
                    videoEl.playsInline = true;
                    videoEl.muted = true;
                    videoEl.loop = true;
                    videoEl.play().catch((err: any) => console.warn('[Portal] Video play failed:', err));
                }

                // Cache elements globally to prevent garbage collection
                (window as any).foveaiPortalStream = stream;
                (window as any).foveaiPortalVideo = videoEl;

                const videoTexture = new THREE.VideoTexture(videoEl);
                videoTexture.colorSpace = THREE.SRGBColorSpace;

                if (spatialPortalMaterial) {
                    spatialPortalMaterial.map = videoTexture;
                    spatialPortalMaterial.color.setHex(0xffffff); // Clear baseline color
                    spatialPortalMaterial.needsUpdate = true;
                }

                dashboard.log('[XR] Spatial Mirror Portal: Webcam ACTIVE!', '#39ff14');
            }
        } catch (camErr) {
            dashboard.log(`[XR] Spatial Portal camera request failed: ${camErr}`, '#ffaa00');
        }
    })();
}

function initMirrorVADIndicator() {
    if (!spatialPortalMesh) return;

    // Create group for the indicator to hold both dot and text
    const indicatorGroup = new THREE.Group();
    indicatorGroup.name = 'mirror_vad_indicator';
    indicatorGroup.position.set(0.55, 0.36, 0.015); // Top-right local position on the mirror plane

    // 1. Red Recording Dot (2cm radius)
    const dotGeo = new THREE.CircleGeometry(0.02, 32);
    const dotMat = new THREE.MeshBasicMaterial({
        color: 0xff003c,
        transparent: true,
        opacity: 0.0,
        side: THREE.DoubleSide
    });
    mirrorVADDot = new THREE.Mesh(dotGeo, dotMat);
    mirrorVADDot.position.set(-0.06, 0, 0); // Position to the left of the text
    indicatorGroup.add(mirrorVADDot);

    // 2. Text Mesh "VAD ON" (using canvas texture)
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 32;
    const ctx = canvas.getContext('2d');
    if (ctx) {
        ctx.fillStyle = 'rgba(0,0,0,0)'; // Transparent background
        ctx.fillRect(0, 0, 128, 32);
        ctx.font = 'bold 20px "Share Tech Mono", monospace';
        ctx.fillStyle = '#ff003c';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText('VAD ON', 0, 16);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const textGeo = new THREE.PlaneGeometry(0.18, 0.045);
    const textMat = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        opacity: 0.0,
        side: THREE.DoubleSide
    });
    mirrorVADIndicator = new THREE.Mesh(textGeo, textMat);
    mirrorVADIndicator.position.set(0.04, 0, 0); // Position to the right of the dot
    indicatorGroup.add(mirrorVADIndicator);

    spatialPortalMesh.add(indicatorGroup);
    console.log('[XR] Spatial Portal holographic VAD indicator initialized.');
}
function initHolographicPanel() {
    if (!env) return;

    // Expose html2canvas globally so HTMLMesh can access and use it
    (window as any).html2canvas = html2canvas;

    let dashboardDom = document.getElementById('foveai-dashboard');
    if (!dashboardDom) {
        const dashInstance = (window as any).dashboard || (window as any).foveaiDashboard;
        if (dashInstance && typeof dashInstance.getElement === 'function') {
            dashboardDom = dashInstance.getElement();
            document.body.appendChild(dashboardDom!);
            console.log('[XR] Appended foveai-dashboard to body for HTMLMesh rendering.');
        }
    }
    if (!dashboardDom) {
        console.error('[XR] HTML Dashboard DOM element (#foveai-dashboard) not found and cannot be mounted! Cannot build HTMLMesh.');
        return;
    }

    // Patch offsetLeft and offsetTop for HTMLMesh coordinate mapping compatibility
    Object.defineProperty(dashboardDom, 'offsetLeft', {
        get: () => dashboardDom!.getBoundingClientRect().left,
        configurable: true
    });
    Object.defineProperty(dashboardDom, 'offsetTop', {
        get: () => dashboardDom!.getBoundingClientRect().top,
        configurable: true
    });

    // Force-style dashboard for clean 3D projection rendering
    dashboardDom.style.visibility = 'visible';
    dashboardDom.style.opacity = '1';

    // Create the InteractiveGroup to handle controller raycasts and pointer clicks automatically
    const interactiveGroup = new InteractiveGroup();
    interactiveGroup.listenToPointerEvents(env.renderer, env.camera);

    // Register both left and right controllers to the interactive group
    const leftCtrl = env.renderer.xr.getController(0);
    const rightCtrl = env.renderer.xr.getController(1);
    // Commented out to prevent duplicate event dispatching with manual pointer clicks in main.ts
    // interactiveGroup.listenToXRControllerEvents(leftCtrl);
    // interactiveGroup.listenToXRControllerEvents(rightCtrl);
    env.scene.add(interactiveGroup);
    (window as any).interactiveGroup = interactiveGroup;

    // isHTMLMeshPixelTransparent moved to top level scope

    const onControllerSelect = (event: any) => {
        const controller = event.target;
        const tempMatrix = new THREE.Matrix4();
        tempMatrix.identity().extractRotation(controller.matrixWorld);

        const raycaster = new THREE.Raycaster();
        raycaster.ray.origin.setFromMatrixPosition(controller.matrixWorld);
        raycaster.ray.direction.set(0, 0, -1).applyMatrix4(tempMatrix);

        const targets: THREE.Object3D[] = [];
        if (holographicPanelMesh && holographicPanelMesh.visible) {
            targets.push(holographicPanelMesh);
        }
        const hud3d = (window as any).xr3dHudMesh;
        if (hud3d && hud3d.visible) {
            targets.push(hud3d);
        }
        const peripheral = (window as any).xrPeripheralHudMesh;
        if (peripheral && peripheral.visible) {
            targets.push(peripheral);
        }

        if (targets.length > 0) {
            let intersects = raycaster.intersectObjects(targets, true);
            
            // Filter out hits on transparent pixels of HTMLMesh objects
            intersects = intersects.filter(hit => {
                let targetObj = hit.object;
                while (targetObj && targetObj !== env.scene) {
                    if (targetObj === hud3d || targetObj === peripheral) {
                        return !isHTMLMeshPixelTransparent(hit);
                    }
                    targetObj = targetObj.parent as any;
                }
                return true;
            });

            if (intersects.length > 0) {
                const intersect = intersects[0];
                const uv = intersect.uv;
                if (uv) {
                    // Find the parent mesh which was added to interactiveGroup to dispatch click to
                    let targetObj = intersect.object;
                    while (targetObj && targetObj !== env.scene) {
                        if (targetObj === holographicPanelMesh || targetObj === hud3d || targetObj === peripheral) {
                            break;
                        }
                        targetObj = targetObj.parent as any;
                    }
                    if (targetObj) {
                        (targetObj as any).dispatchEvent({
                            type: 'click',
                            data: new THREE.Vector2(uv.x, 1 - uv.y)
                        });
                    }
                }
            }
        }
    };

    leftCtrl.addEventListener('select', onControllerSelect);
    rightCtrl.addEventListener('select', onControllerSelect);

    // Create the HTMLMesh wrapping the dashboard DOM element
    const dashboardMesh = new HTMLMesh(dashboardDom);
    dashboardMesh.name = 'holographic_panel';
    dashboardMesh.visible = false;
    if (dashboardMesh.material) {
        if (Array.isArray(dashboardMesh.material)) dashboardMesh.material.forEach((m: any) => m.depthWrite = false);
        else (dashboardMesh.material as any).depthWrite = false;
    }

    // Scale the dashboard mesh to be comfortably readable in VR (approx. 2.2x scale)
    dashboardMesh.scale.setScalar(2.2);

    interactiveGroup.add(dashboardMesh);
    holographicPanelMesh = dashboardMesh as any;

    // Store ONLY the dashboard mesh in uiMeshes for the manual raycaster.
    // HUD meshes (xr3dHudMesh, peripheralMesh) are in interactiveGroup for click handling
    // but must NOT be in uiMeshes — they block the laser from reaching the holographic panel.
    (window as any).foveaiUiMeshes = [dashboardMesh];

    // Ensure HTMLMesh redraws when any input value changes (since MutationObserver ignores value changes)
    dashboardDom.addEventListener('input', () => {
        if (holographicPanelMesh) {
            try {
                (holographicPanelMesh.material as any).map.update();
            } catch (e) { }
        }
    });

    isDevModeActive = false;
    (window as any).isDevModeActive = false;

    // XR-IDE Dev HUD
    if (!xrIdeHud) {
        xrIdeHud = new XrIdeHud();
        xrIdeHud.build(env.scene, env.camera);
    }

    // Create the 3D HUD Mesh wrapping the indicator hub DOM element
    const hubEl = document.getElementById('xr-indicator-hub');
    if (hubEl) {
        const hud3dMesh = new HTMLMesh(hubEl);
        hud3dMesh.name = 'xr_3d_hud';
        hud3dMesh.visible = false;
        if (hud3dMesh.material) {
            if (Array.isArray(hud3dMesh.material)) hud3dMesh.material.forEach((m: any) => m.depthWrite = false);
            else (hud3dMesh.material as any).depthWrite = false;
        }
        hud3dMesh.scale.setScalar(1.9); // −5% from original 2.0
        hud3dMesh.position.set(0, -0.15, -1.2); // 1.2m in front; shifted 10% down (−0.15m) from original
        env.scene.add(hud3dMesh); // Add to scene graph
        interactiveGroup.add(hud3dMesh); // Make clickable via raycasts
        (window as any).xr3dHudMesh = hud3dMesh;
        // Add to foveaiUiMeshes for raycasting, transparency filter handles overlap
        if ((window as any).foveaiUiMeshes) {
            (window as any).foveaiUiMeshes.push(hud3dMesh);
        }
    }

    // Create compact peripheral HUD mesh — small icon strip anchored below center gaze
    const peripheralHubEl = document.getElementById('xr-peripheral-hud');
    if (peripheralHubEl) {
        const peripheralMesh = new HTMLMesh(peripheralHubEl);
        peripheralMesh.name = 'xr_peripheral_hud';
        if (peripheralMesh.material) {
            if (Array.isArray(peripheralMesh.material)) peripheralMesh.material.forEach((m: any) => m.depthWrite = false);
            else (peripheralMesh.material as any).depthWrite = false;
        }
        // Scale: 1200px wide div → ~0.8m wide at scale 0.00066
        peripheralMesh.scale.set(0.00066, 0.00066, 0.00066);
        // Position: below center at 0.8m depth — sits at bottom peripheral vision
        peripheralMesh.position.set(0, -0.30, -0.8);
        const hudEnabled = localStorage.getItem('foveai_3d_hud_enabled') !== 'false';
        peripheralMesh.visible = hudEnabled;
        interactiveGroup.add(peripheralMesh); // Add to interactiveGroup to allow clicks
        (window as any).xrPeripheralHudMesh = peripheralMesh;
        // Add to foveaiUiMeshes for raycasting
        if ((window as any).foveaiUiMeshes) {
            (window as any).foveaiUiMeshes.push(peripheralMesh);
        }
    }

    console.log('[XR] HTML Dashboard Mesh & XR-IDE HUD successfully initialized in world space.');
}



function drawHolographicPanel() {
    if (!holographicPanelCanvas || !holographicPanelTexture) return;
    // Guard: never let a draw error crash the XR animation loop
    try {
        const cw = holographicPanelCanvas.width;
        const ch = holographicPanelCanvas.height;
        const ctx = holographicPanelCanvas.getContext('2d');
        if (!ctx) return;

        // --- Background (fillRect — roundRect not universally supported in WebXR) ---
        ctx.clearRect(0, 0, cw, ch);
        const grad = ctx.createLinearGradient(0, 0, 0, ch);
        grad.addColorStop(0, 'rgba(2, 8, 22, 0.97)');
        grad.addColorStop(1, 'rgba(4, 14, 32, 0.97)');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, cw, ch);

        // Scanline overlay (single gradient — no loop to avoid frame stutter)
        const scanGrad = ctx.createLinearGradient(0, 0, 0, ch);
        scanGrad.addColorStop(0, 'rgba(0,243,255,0.025)');
        scanGrad.addColorStop(0.5, 'rgba(0,0,0,0)');
        scanGrad.addColorStop(1, 'rgba(0,243,255,0.015)');
        ctx.fillStyle = scanGrad;
        ctx.fillRect(0, 0, cw, ch);

        // --- Cyan border (strokeRect — no shadowBlur, no roundRect) ---
        ctx.strokeStyle = '#00f3ff';
        ctx.lineWidth = 6;
        ctx.strokeRect(3, 3, cw - 6, ch - 6);

        // Inner subtle border
        ctx.strokeStyle = 'rgba(0, 243, 255, 0.25)';
        ctx.lineWidth = 2;
        ctx.strokeRect(14, 14, cw - 28, ch - 28);

        // --- Header ---
        const now = new Date();
        const timeStr = now.toLocaleTimeString();
        ctx.font = 'bold 56px Orbitron, monospace';
        ctx.fillStyle = '#00f3ff';
        ctx.fillText('\u2b21 FoveAI // SETTINGS', 60, 90);
        ctx.font = '32px monospace';
        ctx.fillStyle = 'rgba(0, 243, 255, 0.5)';
        ctx.textAlign = 'right';
        ctx.fillText(timeStr, cw - 60, 80);
        ctx.textAlign = 'left';

        // Header divider
        ctx.strokeStyle = 'rgba(0, 243, 255, 0.4)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(60, 110);
        ctx.lineTo(cw - 60, 110);
        ctx.stroke();

        // --- Status Cards Row ---
        const isDev = !!(window as any).isDevModeActive;
        const isListening = !!(window as any).dashboard?.isListening;
        const isSpeaking = !!(window as any).foveaiIsSpeaking;
        const cards = [
            { icon: '\ud83d\udc69', label: 'IDENTITY', value: 'JEN', color: '#ff007f' },
            { icon: '\ud83d\udee0', label: 'DEV MODE', value: isDev ? 'ACTIVE' : 'OFFLINE', color: isDev ? '#39ff14' : '#ff5500' },
            { icon: '\ud83c\udf99', label: 'VAD', value: isListening ? 'LISTENING' : 'STANDBY', color: isListening ? '#39ff14' : '#00f3ff' },
            { icon: '\ud83d\udd0a', label: 'TTS', value: isSpeaking ? 'SPEAKING' : 'IDLE', color: isSpeaking ? '#ffaa00' : '#aaaaaa' },
        ];
        const cardW = Math.floor((cw - 120 - 30 * (cards.length - 1)) / cards.length);
        const cardH = 160;
        const cardY = 140;
        cards.forEach((c, i) => {
            const cx = 60 + i * (cardW + 30);
            // Card background
            ctx.fillStyle = 'rgba(0, 4, 12, 0.7)';
            ctx.fillRect(cx, cardY, cardW, cardH);
            // Card border (no shadowBlur)
            ctx.strokeStyle = c.color;
            ctx.lineWidth = 3;
            ctx.strokeRect(cx, cardY, cardW, cardH);
            // Icon
            ctx.font = '48px serif';
            ctx.fillStyle = '#ffffff';
            ctx.fillText(c.icon, cx + 16, cardY + 62);
            // Label
            ctx.font = 'bold 26px Orbitron, monospace';
            ctx.fillStyle = c.color;
            ctx.fillText(c.label, cx + 80, cardY + 52);
            // Value
            ctx.font = '32px monospace';
            ctx.fillStyle = '#ffffff';
            ctx.fillText(c.value, cx + 80, cardY + 96);
        });

        // --- Chat history ---
        const chatLog = (window as any).foveaiChatLog as { role: string; content: string }[] | undefined;
        const msgs = chatLog ? chatLog.slice(-6) : [];
        const chatY = cardY + cardH + 50;

        // Chat area background
        ctx.fillStyle = 'rgba(0, 4, 12, 0.5)';
        ctx.fillRect(60, chatY - 10, cw - 120, ch - chatY - 80);
        ctx.strokeStyle = 'rgba(0, 243, 255, 0.2)';
        ctx.lineWidth = 1;
        ctx.strokeRect(60, chatY - 10, cw - 120, ch - chatY - 80);

        ctx.font = '30px monospace';
        let lineY = chatY + 30;
        for (const msg of msgs) {
            const isUser = msg.role === 'user';
            const color = isUser ? '#00f3ff' : '#ff007f';
            const prefix = isUser ? '\ud83e\uddd1 YOU: ' : '\ud83d\udc69 JEN: ';
            // Truncate long messages
            const raw = prefix + msg.content;
            const maxChars = Math.floor((cw - 160) / 18);
            const text = raw.length > maxChars ? raw.slice(0, maxChars) + '…' : raw;
            ctx.fillStyle = color;
            ctx.fillText(text, 80, lineY);
            lineY += 46;
            if (lineY > ch - 120) break;
        }
        if (msgs.length === 0) {
            ctx.fillStyle = 'rgba(0, 243, 255, 0.35)';
            ctx.fillText('[ Speak to begin \u2014 VAD is active ]', 80, chatY + 40);
        }

        // --- Footer hint ---
        ctx.fillStyle = 'rgba(0, 4, 12, 0.8)';
        ctx.fillRect(0, ch - 58, cw, 58);
        ctx.strokeStyle = 'rgba(0, 243, 255, 0.3)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, ch - 58);
        ctx.lineTo(cw, ch - 58);
        ctx.stroke();
        ctx.font = '26px monospace';
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.fillText('[ X ] MENU   [ B ] VAD   [ A ] SNAP   [ THUMBSTICK ] SWITCH TABS', 60, ch - 22);

        holographicPanelTexture.needsUpdate = true;
    } catch (e) {
        console.warn('[XR HUD] drawHolographicPanel error (non-fatal):', e);
    }
}
(window as any).updateMenuTexture = drawHolographicPanel;









function handleHolographicClick(x: number, y: number) {
    // Stubbed: HTMLMesh InteractiveGroup now handles clicks automatically!
}

function handleHolographicHover(x: number, y: number) {
    // Stubbed: HTMLMesh InteractiveGroup now handles hover automatically!
}

function toggleHolographicPanel(force?: boolean) {
    if (!holographicPanelMesh || !env) return;
    const show = (force !== undefined) ? force : !holographicPanelMesh.visible;
    holographicPanelMesh.visible = show;

    if (!show) {
        if (isDraggingMenu && holographicPanelMesh) {
            if (originalParent) {
                originalParent.attach(holographicPanelMesh);
            } else {
                env.scene.attach(holographicPanelMesh);
            }
            isDraggingMenu = false;
            draggingHand = null;
            originalParent = null;
        }
    }

    // Let the xrIdeHud's visibility match the dev mode state when showing the panel, otherwise hide it
    if (xrIdeHud) {
        xrIdeHud.setVisible(isDevModeActive && show);
    }

    if (show) {
        // Use XR camera when in an active XR session — env.camera is the static desktop
        // rig camera and won't reflect the headset's actual world position/orientation
        const camera = env.renderer.xr.isPresenting ? env.renderer.xr.getCamera() : env.camera;
        if (!camera) return;
        const cameraPos = new THREE.Vector3();
        const cameraQuat = new THREE.Quaternion();
        try {
            if (env.renderer.xr.isPresenting && camera.matrixWorld) {
                cameraPos.setFromMatrixPosition(camera.matrixWorld);
                cameraQuat.setFromRotationMatrix(camera.matrixWorld);
            } else {
                camera.getWorldPosition(cameraPos);
                camera.getWorldQuaternion(cameraQuat);
            }
        } catch (err) {
            console.error('[XR] Error extracting camera position/rotation from matrixWorld:', err);
            try {
                camera.getWorldPosition(cameraPos);
                camera.getWorldQuaternion(cameraQuat);
            } catch (err2) {
                console.error('[XR] Fallback getWorldPosition failed:', err2);
            }
        }
        const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(cameraQuat);
        // 1.5m is the ergonomic sweet spot per Meta comfort guidelines for large panels
        holographicPanelMesh.position.copy(cameraPos).addScaledVector(dir, 1.5);
        holographicPanelMesh.position.y -= 0.4; // Offset down so the massive 1.8m panel doesn't crash into the ceiling
        holographicPanelMesh.lookAt(cameraPos);
        drawHolographicPanel();
    } else {
        if (holographicCursorMesh) holographicCursorMesh.visible = false;
        if (holographicCursorRight) holographicCursorRight.visible = false;
        if (laserBeam) (laserBeam.material as THREE.LineBasicMaterial).opacity = 0.0;
        if (laserBeamRight) (laserBeamRight.material as THREE.LineBasicMaterial).opacity = 0.0;
        showVirtualKeyboard = false;
        holographicInputText = '';
    }
}

function updateUserAvatar() {
    if (!env || !userAvatarGroup) return;

    // Dynamically position the mirror portal between user and Jen's head, completely invisible to the user (Layer 1)
    if (spatialPortalMesh) {
        spatialPortalMesh.layers.set(1);
        spatialPortalMesh.traverse((child) => child.layers.set(1));
        if (spatialPortalBorder) {
            spatialPortalBorder.layers.set(1);
            spatialPortalBorder.traverse((child) => child.layers.set(1));
        }

        if (avatar && avatar.vrm) {
            const avatarPos = new THREE.Vector3();
            const headBone = avatar.vrm.humanoid?.getNormalizedBoneNode('head');
            if (headBone) {
                headBone.getWorldPosition(avatarPos);
            } else {
                avatarPos.copy(avatar.vrm.scene.position);
                avatarPos.y += 1.3; // Fallback
            }

            const userPos = env.camera.position;
            const toUser = new THREE.Vector3().subVectors(userPos, avatarPos);
            const distance = toUser.length();

            if (distance > 0.1) {
                const dir = toUser.clone().normalize();
                const upVec = new THREE.Vector3(0, 1, 0);
                const leftVec = new THREE.Vector3().crossVectors(upVec, dir).normalize();

                // Position 0.8 meters forward, 0.35 meters to her left, and 0.2 meters down
                spatialPortalMesh.position.copy(avatarPos)
                    .addScaledVector(dir, 0.8)
                    .addScaledVector(leftVec, 0.35)
                    .addScaledVector(upVec, -0.2);

                // Look at the user's head so it aligns perpendicular to the user
                spatialPortalMesh.lookAt(userPos.x, userPos.y, userPos.z);
            }

            if (spatialPortalBorder) {
                spatialPortalBorder.position.copy(spatialPortalMesh.position);
                spatialPortalBorder.quaternion.copy(spatialPortalMesh.quaternion);
            }
        }
    }

    const session = (window as any).xrSession;
    // Show only when in an active immersive session
    userAvatarGroup.visible = !!session;
    if (!session) return;

    // Wake up/play the mirror portal webcam video if the WebXR transition paused it
    const videoEl = (window as any).foveaiPortalVideo as HTMLVideoElement | null;
    if (videoEl && videoEl.paused) {
        videoEl.play().catch(() => { });
    }

    // 1. Update Head (tracks camera)
    if (userHead) {
        userHead.position.copy(env.camera.position);
        userHead.quaternion.copy(env.camera.quaternion);
    }

    // 2. Update Torso (sitting-aware dynamic posture with tilt tracking)
    if (userTorso) {
        const headPos = env.camera.position;
        const headY = headPos.y;

        // Estimate neck position slightly below head
        const neckPos = new THREE.Vector3().copy(headPos);
        neckPos.y -= 0.15;

        // Dynamic hip height calculation: standing vs sitting transition
        // standard hip height is headY - 0.75m. If sitting, cap at 0.45m chair height.
        let hipY = headY - 0.75;
        if (hipY < 0.45) {
            hipY = 0.45; // Fixed chair height boundary
        }
        // Prevent hips going above neck if camera is extremely low
        if (hipY >= neckPos.y) {
            hipY = Math.max(0.1, neckPos.y - 0.2);
        }

        // Offset hips horizontally based on head pitch rotation (standing, leaning forward vs sofa leaning back)
        const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(env.camera.quaternion);
        forward.y = 0; // horizontal projection
        if (forward.lengthSq() > 0.001) {
            forward.normalize();
        } else {
            forward.set(0, 0, -1);
        }

        // Pitch check: negative value means headset is looking upwards (leaning back on sofa)
        const euler = new THREE.Euler().setFromQuaternion(env.camera.quaternion, 'YXZ');
        const isLeaningBack = euler.x < -0.05; // Leaning back on comfortable sofa/chair
        const offsetDist = isLeaningBack ? 0.20 : -0.15; // 20cm in front of head when leaning back, 15cm behind when standing/leaning forward

        const hipPos = new THREE.Vector3().copy(headPos);
        hipPos.y = hipY;
        hipPos.addScaledVector(forward, offsetDist);

        // Compute torso direction and size
        const torsoVec = new THREE.Vector3().subVectors(neckPos, hipPos);
        const torsoHeight = Math.max(0.1, torsoVec.length());

        // Scale the cylinder (default height is 1.0)
        userTorso.scale.set(1, torsoHeight, 1);

        // Midpoint position
        userTorso.position.copy(hipPos).addScaledVector(torsoVec, 0.5);

        // Rotate torso cylinder (oriented along local Y-axis) to align with torsoVec
        const targetDir = torsoVec.clone().normalize();
        userTorso.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), targetDir);
    }

    // 3. Update Hands (track controllers)
    const leftCtrl = env.renderer.xr.getController(0);
    const rightCtrl = env.renderer.xr.getController(1);

    if (userLeftHand && leftCtrl) {
        leftCtrl.getWorldPosition(userLeftHand.position);
        leftCtrl.getWorldQuaternion(userLeftHand.quaternion);
    }
    if (userRightHand && rightCtrl) {
        rightCtrl.getWorldPosition(userRightHand.position);
        rightCtrl.getWorldQuaternion(userRightHand.quaternion);
    }

    // Pulse the neon borders of the mirror portal over time using clock
    if (spatialPortalBorderMaterial) {
        const time = clock.getElapsedTime();
        spatialPortalBorderMaterial.emissiveIntensity = 1.0 + Math.sin(time * 3.0) * 0.6;
    }

    // Update mirror VAD indicator based on active microphone VAD listening state
    if (mirrorVADDot && mirrorVADIndicator) {
        const isListening = dashboard.isListening;
        const targetOpacity = isListening ? 1.0 : 0.0;

        // Lerp opacity smoothly
        (mirrorVADDot.material as THREE.MeshBasicMaterial).opacity += (targetOpacity - (mirrorVADDot.material as THREE.MeshBasicMaterial).opacity) * 0.15;
        (mirrorVADIndicator.material as THREE.MeshBasicMaterial).opacity += (targetOpacity - (mirrorVADIndicator.material as THREE.MeshBasicMaterial).opacity) * 0.15;

        // Pulsing scale animation for the recording dot when active
        if (isListening) {
            const pulse = 1.0 + Math.sin(clock.getElapsedTime() * 8.0) * 0.25;
            mirrorVADDot.scale.set(pulse, pulse, 1);
        } else {
            mirrorVADDot.scale.set(1, 1, 1);
        }
    }
}

// --- BRAIN RESPONSE QUALITY GUARD ---
// The local WebLLM can produce semi-coherent but clearly broken output when
// under-initialized (e.g. "I'm here but my thoughts haven't crystallized yet").
// These pass the basic empty/[ERROR] check but must NOT be spoken via TTS —
// they are effectively wrapped error messages from a non-functional mind.
let _lastBrainResponse = '';
let _brainRepeatCount = 0;

function isBrokenBrainResponse(response: string | null | undefined): boolean {
    if (!response || !response.trim()) return true;
    if (response.trim().startsWith('[ERROR]')) return true;

    const r = response.trim().toLowerCase();

    // Known broken-brain patterns from under-initialized local models
    const brokenPatterns = [
        'crystallized',
        'crystalized',
        'crystallising',
        'crystallizing',
        'thoughts haven',
        'thoughts havent',
        'connection stabilising',
        'connection stabilizing',
        'central mind is warming',
        'try again in a moment',
        'neural link stabilising',
        'neural link stabilizing',
        'waiting for the user',
        'waiting for user',
        'waiting to speak',
    ];

    for (const pattern of brokenPatterns) {
        if (r.includes(pattern)) return true;
    }

    // Stuck loop: same response repeated 2+ times → brain is not functional
    if (r === _lastBrainResponse) {
        _brainRepeatCount++;
        if (_brainRepeatCount >= 2) return true;
    } else {
        _lastBrainResponse = r;
        _brainRepeatCount = 0;
    }

    return false;
}

// --- SOUNDBOARD CONTEXT CONDENSER ---
// The backend /api/soundboard/context returns a very verbose descriptive text.
// Models ignore long suggestive instructions. This condenser replaces it with
// a short, IMPERATIVE context with concrete before/after examples showing
// Jen HOW to use bracket tokens instead of just describing them.
function condenseSoundboardContext(tags: string[]): string {
    const tagList = tags.join(', ');
    return [
        "=== NON-VERBAL EXPRESSION (MANDATORY) ===",
        "You MUST use soundboard bracket tokens in EVERY response to express emotion non-verbally.",
        "This is not optional — bracket tokens are how you laugh, sigh, gasp, and emote.",
        "",
        "Available tags: " + tagList,
        "",
        "Bracket types:",
        "  <audio:tag> — instant sound (bypasses TTS, lowest latency)",
        "  <flavour:tag> — subtle sound blended with your TTS voice",
        "  <emotion:tag> — face BlendShape (happy, sad, surprised, curious, content, neutral, angry, fearful)",
        "  <request:description> — generate a NEW sound and add it to your soundboard (always works)",
        "",
        "=== EXAMPLES — DO THIS, NOT THAT ===",
        'BAD:  "Oh, that\'s interesting! I could use a sound here..."',
        'GOOD: "Oh! <audio:oh_realization> That\'s fascinating! <flavour:hmm_thoughtful>"',
        '',
        'BAD:  "I\'m happy to hear that."',
        'GOOD: "<audio:laugh_soft> I\'m so glad! <emotion:happy>"',
        '',
        'BAD:  "Let me think about that..."',
        'GOOD: "<flavour:hmm_thoughtful> Hmm... <request:soft contemplative hum>"',
        '',
        'BAD:  "That\'s a relief."',
        'GOOD: "<audio:sigh_content> Ah, much better. <flavour:mhm_affirming>"',
        '',
        "=== RULES ===",
        "1. Use 1-3 bracket tokens per response — mix types for richness",
        "2. Place tokens WHERE the emotion occurs in your text, not clustered at the end",
        "3. If no existing tag fits your emotion, GENERATE a new one: <request:soft curious hum>",
        "4. NEVER describe or mention the soundboard system — just USE the bracket tokens",
        "5. <request:description> keywords: gasp, laugh, sigh, hmm, oh, chuckle, whisper, hum, chime, sparkle, thunder, rain, fire, wind, ethereal, magical, warm, melodic, bright, dark, soft, gentle, distant",
    ].join('\n');
}

// --- DESKTOP CONTROLS ---
if (env) {
    const controls = new OrbitControls(env.camera, env.renderer.domElement);
    controls.target.set(-0.2, 0.8, -1.2); // Slightly left to feel natural with the hidden sidebar
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    env.camera.position.set(-0.2, 1.2, 0.5);
    controls.update();

    // --- XR CONTROLLERS ---
    const controllerModelFactory = new XRControllerModelFactory();

    const controller1 = env.renderer.xr.getController(0);
    const controller2 = env.renderer.xr.getController(1);
    env.scene.add(controller1);
    env.scene.add(controller2);

    wandLeft = new HapticWand(controller1, 0x00f3ff);
    wandRight = new HapticWand(controller2, 0x00f3ff); // Both cyan — arm-extension style
    // Meshes are self-parented inside HapticWand constructor (parent.add(this.mesh))

    // Load controller models for visual representation
    const controllerGrip1 = controllerModelFactory.createControllerModel(controller1);
    const controllerGrip2 = controllerModelFactory.createControllerModel(controller2);
    controller1.add(controllerGrip1);
    controller2.add(controllerGrip2);

    // Create teleport marker (arc indicator)
    const teleportGeo = new THREE.RingGeometry(0.15, 0.25, 32);
    const teleportMat = new THREE.MeshStandardMaterial({
        color: 0x00f3ff,
        emissive: 0x00f3ff,
        emissiveIntensity: 0.8,
        transparent: true,
        opacity: 0.0
    });
    teleportMarker = new THREE.Mesh(teleportGeo, teleportMat);
    teleportMarker.rotation.x = -Math.PI / 2;
    teleportMarker.name = 'teleport_marker';
    env.scene.add(teleportMarker);

    // Create laser pointer beams (left and right controller pointing tools)
    // --- NATIVE-STYLE WHITE FADED RAY POINTERS ---
    // Replicate Meta Quest's native pointer look: white gradient line + white sphere dot at hit.
    // depthTest:false + renderOrder:999 ensures they're always drawn on top of HTMLMesh surfaces.
    const RAY_LENGTH = 5.0;
    const rayPoints: THREE.Vector3[] = [];
    const RAY_SEGS = 12;
    for (let i = 0; i <= RAY_SEGS; i++) rayPoints.push(new THREE.Vector3(0, 0, -i * (RAY_LENGTH / RAY_SEGS)));

    function makeRayLine(): THREE.Line {
        const geo = new THREE.BufferGeometry().setFromPoints(rayPoints);
        // Per-vertex alpha fading: bright at tip (1.0) → faint at far end (0.05)
        const alphas = new Float32Array(RAY_SEGS + 1);
        for (let i = 0; i <= RAY_SEGS; i++) alphas[i] = 1.0 - (i / RAY_SEGS) * 0.95;
        geo.setAttribute('alpha', new THREE.BufferAttribute(alphas, 1));
        const mat = new THREE.LineBasicMaterial({
            color: 0xffffff,
            transparent: true,
            opacity: 0.55,
            depthTest: false,
            depthWrite: false,
        });
        const line = new THREE.Line(geo, mat);
        line.renderOrder = 999;
        return line;
    }

    laserBeam = makeRayLine();
    laserBeam.name = 'laser_pointer_left';
    laserBeam.visible = false;
    env.scene.add(laserBeam);

    laserBeamRight = makeRayLine();
    laserBeamRight.name = 'laser_pointer_right';
    laserBeamRight.visible = false;
    env.scene.add(laserBeamRight);

    // White sphere dot — the hit-point indicator (replaces ring cursor)
    const dotGeo = new THREE.SphereGeometry(0.008, 12, 8);
    const dotMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.90,
        depthTest: false,
        depthWrite: false,
    });
    holographicCursorMesh = new THREE.Mesh(dotGeo, dotMat);
    holographicCursorMesh.name = 'holographic_cursor_left';
    holographicCursorMesh.renderOrder = 999;
    holographicCursorMesh.visible = false;
    env.scene.add(holographicCursorMesh);

    const dotGeoR = new THREE.SphereGeometry(0.008, 12, 8);
    const dotMatR = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.90,
        depthTest: false,
        depthWrite: false,
    });
    holographicCursorRight = new THREE.Mesh(dotGeoR, dotMatR);
    holographicCursorRight.name = 'holographic_cursor_right';
    holographicCursorRight.renderOrder = 999;
    holographicCursorRight.visible = false;
    env.scene.add(holographicCursorRight);
}

// --- GLOBAL ERROR CATCHER ---
window.onerror = (msg, url, line, col, error) => {
    const errorMsg = `FATAL: ${msg} @ ${line}:${col}`;
    console.error(errorMsg, error);
    if (dashboard) dashboard.log(errorMsg, '#ff007f');
    return false;
};

// --- XR DOM OVERLAY CONTAINER ---
// WebXR dom-overlay renders these elements on top of the XR scene in AR mode.
// Without this, DOM elements like the Dashboard are invisible in immersive XR.
const xrOverlay = document.createElement('div');
xrOverlay.id = 'xr-dom-overlay';
xrOverlay.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; pointer-events:none; z-index:1001;';
document.body.appendChild(xrOverlay);

// Recording indicator for Push-to-Talk (visible in XR overlay)
const xrRecordingIndicator = document.createElement('div');
xrRecordingIndicator.id = 'xr-recording-indicator';
xrRecordingIndicator.innerHTML = '<div class="rec-dot"></div><span>REC</span>';
xrRecordingIndicator.style.cssText = 'position:fixed; top:30px; left:50%; transform:translateX(-50%); display:none; align-items:center; gap:10px; padding:10px 24px; background:rgba(255,0,0,0.5); border:2px solid #ff007f; border-radius:25px; color:#ff007f; font-family:Orbitron,sans-serif; font-size:1rem; letter-spacing:3px; pointer-events:none; z-index:1002; backdrop-filter:blur(10px); box-shadow:0 0 20px rgba(255,0,127,0.4);';
xrOverlay.appendChild(xrRecordingIndicator);

// Snapshot flash effect
const xrSnapshotFlash = document.createElement('div');
xrSnapshotFlash.id = 'xr-snapshot-flash';
xrSnapshotFlash.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; background:white; opacity:0; pointer-events:none; transition:opacity 0.15s ease-out; z-index:1003;';
xrOverlay.appendChild(xrSnapshotFlash);

// Audio unlock prompt — visible in XR overlay when audio is suspended (Quest 3)
const xrAudioPrompt = document.createElement('div');
xrAudioPrompt.id = 'xr-audio-prompt';
xrAudioPrompt.innerHTML = '[AUD] TAP ANYWHERE TO ENABLE AUDIO';
xrAudioPrompt.style.cssText = 'position:fixed; bottom:80px; left:50%; transform:translateX(-50%); display:none; align-items:center; gap:10px; padding:12px 24px; background:rgba(0,243,255,0.15); border:2px solid var(--neon-blue); border-radius:30px; color:var(--neon-blue); font-family:Orbitron,sans-serif; font-size:0.8rem; letter-spacing:2px; pointer-events:auto; z-index:1004; backdrop-filter:blur(10px); cursor:pointer;';
xrOverlay.appendChild(xrAudioPrompt);
// Show prompt after 2.5s if audio is still suspended
setTimeout(() => {
    try {
        const testCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
        if (testCtx.state === 'suspended') {
            xrAudioPrompt.style.display = 'flex';
        }
        testCtx.close();
    } catch { }
}, 2500);
// Tap prompt also unlocks audio
xrAudioPrompt.addEventListener('click', () => { audio.unlockAudio(); xrAudioPrompt.style.display = 'none'; });
xrAudioPrompt.addEventListener('touchstart', () => { audio.unlockAudio(); xrAudioPrompt.style.display = 'none'; });

// Controller status indicator — query existing element inside the dashboard telemetry strip
const xrControllerStatus = document.getElementById('xr-controller-status') || (() => {
    const el = document.createElement('div');
    el.id = 'xr-controller-status';
    xrOverlay.appendChild(el);
    return el;
})();

// Recording dot animation + Indicator HUD Overlay styling
const xrOverlayStyle = document.createElement('style');
xrOverlayStyle.textContent = '#xr-recording-indicator .rec-dot{width:10px;height:10px;border-radius:50%;background:#ff007f;animation:xr-rec-pulse 1s infinite} @keyframes xr-rec-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.3;transform:scale(0.6)}} #xr-audio-prompt{animation:xr-audio-pulse 2s infinite} @keyframes xr-audio-pulse{0%,100%{opacity:1;box-shadow:0 0 10px rgba(0,243,255,0.3)}50%{opacity:0.7;box-shadow:0 0 25px rgba(0,243,255,0.6)}} #foveai-dashboard.xr-menu-flash{animation:xr-menu-flash 0.4s ease-out} @keyframes xr-menu-flash{0%{box-shadow:-5px 0 30px rgba(0,243,255,0.6)}100%{box-shadow:-10px 0 30px rgba(0,0,0,0.5)}} *{user-select:text!important;-webkit-user-select:text!important} #xr-indicator-hub { position:fixed; top:0; left:-20000px; width:1140px; height:714px; pointer-events:none; font-family:\'Orbitron\',sans-serif; color:rgba(255,255,255,0.7); z-index:1005; opacity:0.8; } .xr-hud-top { position:absolute; top:24px; left:38px; right:38px; display:flex; justify-content:space-between; align-items:center; } .xr-hud-bottom-left { position:absolute; bottom:30px; left:38px; display:flex; flex-direction:column; gap:8px; } .xr-hud-bottom-center { position:absolute; bottom:30px; left:50%; transform:translateX(-50%); display:flex; flex-direction:column; align-items:center; gap:8px; width:320px; max-width:28vw; } .xr-hud-bottom-right { position:absolute; bottom:30px; right:38px; display:flex; flex-direction:column; gap:8px; align-items:flex-end; } .xr-hud-panel { background:rgba(10,15,30,0.15); border:1px solid rgba(255,255,255,0.12); border-radius:6px; padding:8px 16px; display:flex; align-items:center; gap:10px; backdrop-filter:blur(8px); box-shadow:0 0 10px rgba(255,255,255,0.03); color:rgba(255,255,255,0.7); } .xr-hud-panel-pink { border-color:rgba(255,0,127,0.2); background:rgba(255,0,127,0.04); box-shadow:none; } .xr-hud-panel-green { border-color:rgba(57,255,20,0.2); background:rgba(57,255,20,0.04); box-shadow:none; } .xr-hud-panel-cyan { border-color:rgba(0,243,255,0.2); background:rgba(0,243,255,0.04); box-shadow:none; } .xr-hud-panel-orange { border-color:rgba(255,120,0,0.2); background:rgba(255,120,0,0.04); box-shadow:none; } .xr-hud-panel-red-flash { border-color:rgba(255,0,0,0.4); background:rgba(255,0,0,0.05); box-shadow:none; animation:xr-hud-alert-flash 1s infinite alternate; } @keyframes xr-hud-alert-flash { 0% { border-color:rgba(255,0,0,0.2); } 100% { border-color:rgba(255,0,0,0.5); } } .xr-hud-icon { font-size:14px; color:rgba(255,255,255,0.6); } .xr-hud-val { font-size:11px; font-weight:bold; letter-spacing:1.5px; font-family:monospace; color:rgba(255,255,255,0.7); } .xr-hud-val-pink { color:rgba(255,255,255,0.75)!important; } .xr-hud-val-green { color:rgba(255,255,255,0.75)!important; } .xr-hud-val-cyan { color:rgba(255,255,255,0.75)!important; } .xr-hud-val-orange { color:rgba(255,255,255,0.75)!important; } .xr-hud-val-red { color:rgba(255,255,255,0.75)!important; } .xr-hud-pulse { animation:xr-hud-pulse-glow 1.5s infinite; } @keyframes xr-hud-pulse-glow { 0%,100%{opacity:1;} 50%{opacity:0.5;} } .xr-hud-pulse-orange { animation:xr-hud-pulse-orange-glow 1.5s infinite; } @keyframes xr-hud-pulse-orange-glow { 0%,100%{opacity:1;} 50%{opacity:0.5;} }';
document.head.appendChild(xrOverlayStyle);

// --- XR HUD INDICATOR HUB ---
const xrIndicatorHub = document.createElement('div');
xrIndicatorHub.id = 'xr-indicator-hub';
xrIndicatorHub.style.display = 'block';
xrIndicatorHub.innerHTML = `
    <div class="xr-hud-top">
        <div id="xr-hud-identity" class="xr-hud-panel">
            <span class="xr-hud-icon">👩</span>
            <span class="xr-hud-val">IDENTITY: JEN COMPANION</span>
        </div>
        <div id="xr-hud-devmode" class="xr-hud-panel" style="cursor:pointer;pointer-events:auto;" title="Click to toggle Developer Bridge">
            <span class="xr-hud-icon">🛠️</span>
            <span class="xr-hud-val">DEV SYSTEM: OFFLINE</span>
        </div>
        <div id="xr-hud-thinking" class="xr-hud-panel" style="display: none;">
            <span class="xr-hud-icon">🧠</span>
            <span class="xr-hud-val">AI THINKING</span>
        </div>
        <div id="xr-hud-listening" class="xr-hud-panel">
            <span class="xr-hud-icon">🎙️</span>
            <span class="xr-hud-val">VAD STANDBY</span>
        </div>
    </div>
    <div class="xr-hud-bottom-left">
        <div id="xr-hud-swarm" class="xr-hud-panel xr-hud-panel-pink">
            <span class="xr-hud-icon">🐝</span>
            <span class="xr-hud-val xr-hud-val-pink">SWARM: 3 AGENTS | $11.45 USDT</span>
        </div>
    </div>
    <div class="xr-hud-bottom-center">
        <div id="xr-hud-dev-feed" class="xr-hud-panel xr-hud-panel-cyan"
             style="width:100%; flex-direction:column; align-items:flex-start; gap:3px; padding:6px 12px;">
            <div style="display:flex; align-items:center; gap:6px;">
                <span class="xr-hud-icon" style="font-size:11px;">🤖</span>
                <span class="xr-hud-val xr-hud-val-cyan" style="font-size:9px; opacity:0.7; letter-spacing:1px;">DEV FEED</span>
            </div>
            <span id="xr-hud-dev-feed-val" class="xr-hud-val xr-hud-val-cyan"
                  style="font-size:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:100%;">WAITING...</span>
        </div>
    </div>
    <div class="xr-hud-bottom-right">
        <div id="xr-hud-telemetry" class="xr-hud-panel xr-hud-panel-green">
            <span class="xr-hud-icon">🖥️</span>
            <span class="xr-hud-val xr-hud-val-green">SYS VITAL</span>
        </div>
    </div>
`;
xrOverlay.appendChild(xrIndicatorHub);

// --- COMPACT PERIPHERAL HUD — Small icon squares at bottom edge of VR viewport ---
// Each icon is a 60×70px semi-transparent tile with a white emoji + tiny label.
// Green background = on/active/healthy. Red background = off/error/crashed.
// Rendered as an HTMLMesh child of the XR camera, placed below center gaze.
const peripheralHudStyle = document.createElement('style');
peripheralHudStyle.textContent = `
#xr-peripheral-hud {
    position: fixed; top: 0; left: -21000px;
    width: 1200px; height: 200px;
    pointer-events: none; z-index: 1006;
    font-family: 'Orbitron', sans-serif;
    display: flex; flex-direction: column; justify-content: flex-end;
}
.xr-prow {
    display: flex; flex-direction: row; align-items: center;
    gap: 8px; padding: 8px 16px; flex-wrap: wrap;
}
.xr-prow-top { justify-content: flex-end; }
.xr-prow-bottom { justify-content: center; }
.xr-picon {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    width: 60px; height: 68px; border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.12);
    backdrop-filter: blur(6px);
    transition: background 0.4s ease;
    cursor: default;
    color: rgba(255,255,255,0.7);
}
.xr-picon-on  { background: rgba(255, 255, 255, 0.08);  border-color: rgba(255,255,255,0.22); }
.xr-picon-off { background: rgba(255, 255, 255, 0.02);  border-color: rgba(255,255,255,0.06); opacity: 0.55; }
.xr-picon-neutral { background: rgba(255, 255, 255, 0.05); border-color: rgba(255,255,255,0.15); }
.xr-picon-warn { background: rgba(255, 0, 0, 0.04); border-color: rgba(255,0,0,0.2); animation: xr-picon-blink 1.2s infinite alternate; }
@keyframes xr-picon-blink { 0% { opacity: 0.6; } 100% { opacity: 1; } }
.xr-picon em { font-size: 22px; line-height: 1; font-style: normal; opacity: 0.7; }
.xr-picon span { font-size: 7.5px; font-weight: bold; letter-spacing: 0.8px; color: rgba(255,255,255,0.7); text-transform: uppercase; margin-top: 3px; text-align: center; line-height: 1.2; }
`;
document.head.appendChild(peripheralHudStyle);

const xrPeripheralHub = document.createElement('div');
xrPeripheralHub.id = 'xr-peripheral-hud';
xrPeripheralHub.innerHTML = `
    <div class="xr-prow xr-prow-top">
        <div id="ph-cpu" class="xr-picon xr-picon-neutral"><em>🖥️</em><span>CPU --%</span></div>
        <div id="ph-gpu" class="xr-picon xr-picon-neutral"><em>⚡</em><span>GPU --%</span></div>
    </div>
    <div class="xr-prow xr-prow-bottom">
        <div id="ph-soul" class="xr-picon xr-picon-neutral"><em>🟢</em><span>Soul</span></div>
        <div id="ph-vad" class="xr-picon xr-picon-off"><em>🎙️</em><span>VAD</span></div>
        <div id="ph-think" class="xr-picon xr-picon-neutral"><em>💬</em><span>Think</span></div>
        <div id="ph-deep" class="xr-picon xr-picon-off"><em>🧠</em><span>Deep</span></div>
        <div id="ph-cloud" class="xr-picon xr-picon-neutral"><em>🌐</em><span>Cloud</span></div>
        <div id="ph-file" class="xr-picon xr-picon-off"><em>📁</em><span>File</span></div>
        <div id="ph-dev" class="xr-picon xr-picon-off" style="cursor:pointer;pointer-events:auto;" title="Toggle Developer Bridge"><em>🛠️</em><span>Dev</span></div>
        <div id="ph-restart" class="xr-picon xr-picon-neutral" style="cursor:pointer;pointer-events:auto;"><em>🔄</em><span>Restart</span></div>
        <div id="ph-quit" class="xr-picon xr-picon-off" style="cursor:pointer;pointer-events:auto;"><em>❌</em><span>Quit</span></div>
    </div>
`;
xrOverlay.appendChild(xrPeripheralHub);

// Peripheral HUD icon visibility state (keyed by icon ID, default all visible)
const PERIPHERAL_HUD_ICONS = ['ph-soul', 'ph-vad', 'ph-think', 'ph-deep', 'ph-cloud', 'ph-file', 'ph-dev', 'ph-restart', 'ph-quit', 'ph-cpu', 'ph-gpu'];
function getPeripheralIconVisible(id: string): boolean {
    return localStorage.getItem(`foveai_hud_icon_${id}_visible`) !== 'false';
}

function updatePeripheralHUD() {
    if (!((window as any).xrSession)) return;

    const setIcon = (id: string, cls: string, emoji: string, label: string) => {
        const el = document.getElementById(id);
        if (!el) return;
        // Visibility toggle from settings
        el.style.display = getPeripheralIconVisible(id) ? 'flex' : 'none';
        el.className = `xr-picon ${cls}`;
        el.innerHTML = `<em>${emoji}</em><span>${label}</span>`;
    };

    // Soul online/offline
    const isSoulReachable = (window as any).foveaiBrainState?.soulReachable !== false;
    setIcon('ph-soul', isSoulReachable ? 'xr-picon-on' : 'xr-picon-warn', isSoulReachable ? '🟢' : '🚨', isSoulReachable ? 'Soul' : 'OFFLINE');

    // VAD listening
    const isListening = dashboard?.isListening || false;
    const isSpeaking = (window as any).foveaiVideoChat?.isSpeaking || false;
    if (isSpeaking) setIcon('ph-vad', 'xr-picon-on', '🗣️', 'Speaking');
    else if (isListening) setIcon('ph-vad', 'xr-picon-on', '🔴', 'Listen');
    else setIcon('ph-vad', 'xr-picon-off', '🎙️', 'VAD');

    // Thought stream toggle
    const thinkOn = dashboard?.showThoughtStream || false;
    setIcon('ph-think', thinkOn ? 'xr-picon-on' : 'xr-picon-off', '💬', 'Think');

    // Deep think toggle
    const deepOn = dashboard?.deepThought || false;
    setIcon('ph-deep', deepOn ? 'xr-picon-on' : 'xr-picon-off', '🧠', 'Deep');

    // Cloud vs local mode
    const cogMode = (window as any).foveaiConfig?.cognitiveMode || 'local';
    const isCloud = cogMode === 'cloud' || cogMode === 'ollama_cloud';
    setIcon('ph-cloud', isCloud ? 'xr-picon-on' : 'xr-picon-neutral', isCloud ? '☁️' : '🏠', isCloud ? 'Cloud' : 'Local');

    // File attachment ready
    const hasFile = !!(window as any).foveaiPendingAttachment;
    setIcon('ph-file', hasFile ? 'xr-picon-on' : 'xr-picon-off', '📁', 'File');

    // Dev mode
    setIcon('ph-dev', isDevModeActive ? 'xr-picon-on' : 'xr-picon-off', '🛠️', isDevModeActive ? 'Dev:ON' : 'Dev');

    // CPU / GPU vitals
    const tData = (window as any).foveaiDashboard?.telemetryData || { CPU_PCT: 0, GPU_PCT: 0 };
    const cpuEl = document.getElementById('ph-cpu');
    if (cpuEl) {
        cpuEl.style.display = getPeripheralIconVisible('ph-cpu') ? 'flex' : 'none';
        const cpuLoad = Math.round(tData.CPU_PCT || 0);
        cpuEl.className = `xr-picon ${cpuLoad > 85 ? 'xr-picon-warn' : cpuLoad > 50 ? 'xr-picon-neutral' : 'xr-picon-on'}`;
        cpuEl.innerHTML = `<em>🖥️</em><span>CPU ${cpuLoad}%</span>`;
    }
    const gpuEl = document.getElementById('ph-gpu');
    if (gpuEl) {
        gpuEl.style.display = getPeripheralIconVisible('ph-gpu') ? 'flex' : 'none';
        const gpuLoad = Math.round(tData.GPU_PCT || 0);
        gpuEl.className = `xr-picon ${gpuLoad > 90 ? 'xr-picon-warn' : gpuLoad > 60 ? 'xr-picon-neutral' : 'xr-picon-on'}`;
        gpuEl.innerHTML = `<em>⚡</em><span>GPU ${gpuLoad}%</span>`;
    }

    // Restart & Quit always visible neutral
    const rstEl = document.getElementById('ph-restart');
    if (rstEl) rstEl.style.display = getPeripheralIconVisible('ph-restart') ? 'flex' : 'none';
    const quitEl = document.getElementById('ph-quit');
    if (quitEl) quitEl.style.display = getPeripheralIconVisible('ph-quit') ? 'flex' : 'none';

    // Refresh 3D texture
    if ((window as any).xrPeripheralHudMesh) {
        try { ((window as any).xrPeripheralHudMesh.material as any).map.update(); } catch (e) { }
    }
}

// Restart backend button
document.getElementById('ph-restart')?.addEventListener('click', async () => {
    try {
        await fetch('/api/soul/restart', { method: 'POST' });
        dashboard.log('[HUD] Backend restart requested', 'var(--neon-pink)');
    } catch (e) { }
});

// Quit XR session button
document.getElementById('ph-quit')?.addEventListener('click', async () => {
    try {
        const sess = (window as any).xrSession as XRSession | null;
        if (sess) await sess.end();
    } catch (e) { }
});

// Dev Bridge toggle — peripheral icon
document.getElementById('ph-dev')?.addEventListener('click', () => {
    toggleDevMode();
});

// Dev Bridge toggle — XRideHud indicator hub panel (also works in 3D HTMLMesh via ray-wand)
document.getElementById('xr-hud-devmode')?.addEventListener('click', () => {
    toggleDevMode();
});


function updateXRIndicatorHub() {
    const hub = document.getElementById('xr-indicator-hub');
    if (!hub) return;

    // Check presenting state
    const isPresenting = !!((window as any).xrSession);
    if (!isPresenting) return;

    // 1. Identity & Dev Mode States
    const identEl = document.getElementById('xr-hud-identity');
    const devModeEl = document.getElementById('xr-hud-devmode');

    if (identEl) {
        if (isDevModeActive) {
            identEl.className = 'xr-hud-panel xr-hud-panel-cyan';
            identEl.innerHTML = `<span class="xr-hud-icon">🤖</span><span class="xr-hud-val xr-hud-val-cyan">IDENTITY: CO-DEVELOPER (GEMINI)</span>`;
        } else {
            identEl.className = 'xr-hud-panel xr-hud-panel-pink';
            identEl.innerHTML = `<span class="xr-hud-icon">👩</span><span class="xr-hud-val xr-hud-val-pink">IDENTITY: JEN COMPANION</span>`;
        }
    }

    if (devModeEl) {
        // Preserve clickability — keep pointer-events and cursor regardless of state
        devModeEl.style.cursor = 'pointer';
        devModeEl.style.pointerEvents = 'auto';
        if (isDevModeActive) {
            devModeEl.className = 'xr-hud-panel xr-hud-panel-cyan';
            devModeEl.innerHTML = `<span class="xr-hud-icon">⚡</span><span class="xr-hud-val xr-hud-val-cyan">DEV SYSTEM: ACTIVE (CODER)</span>`;
        } else {
            devModeEl.className = 'xr-hud-panel';
            devModeEl.innerHTML = `<span class="xr-hud-icon">🛠️</span><span class="xr-hud-val">DEV SYSTEM: OFFLINE</span>`;
        }
    }

    // 2. Speech / VAD listening state
    const isListening = dashboard?.isListening || false;
    const isSpeaking = (window as any).foveaiVideoChat?.isSpeaking || false;

    const listEl = document.getElementById('xr-hud-listening');
    if (listEl) {
        if (isSpeaking) {
            listEl.className = 'xr-hud-panel xr-hud-panel-green';
            listEl.innerHTML = `<span class="xr-hud-icon">🗣️</span><span class="xr-hud-val xr-hud-val-green">JEN SPEAKING</span>`;
        } else if (isListening) {
            listEl.className = 'xr-hud-panel xr-hud-panel-pink';
            listEl.innerHTML = `<span class="xr-hud-icon xr-hud-pulse">🔴</span><span class="xr-hud-val xr-hud-val-pink xr-hud-pulse">VAD LISTENING</span>`;
        } else {
            listEl.className = 'xr-hud-panel';
            listEl.innerHTML = `<span class="xr-hud-icon">🎙️</span><span class="xr-hud-val">VAD STANDBY</span>`;
        }
    }

    // 3. AI Thinking & Radio Shadow Detection
    const thinkingEl = document.getElementById('xr-hud-thinking');
    if (thinkingEl) {
        if (isBrainThinking) {
            const queryDuration = Date.now() - lastBrainQueryStartTime;
            thinkingEl.style.display = 'flex';
            if (queryDuration > 75000) {
                // Radio shadow / network hang warning!
                thinkingEl.className = 'xr-hud-panel xr-hud-panel-red-flash';
                thinkingEl.innerHTML = `<span class="xr-hud-icon">⚠️</span><span class="xr-hud-val xr-hud-val-red">NEURAL SHADOW: HANG DETECTED (${Math.round(queryDuration / 1000)}s)</span>`;
            } else {
                thinkingEl.className = 'xr-hud-panel xr-hud-panel-orange';
                thinkingEl.innerHTML = `<span class="xr-hud-icon xr-hud-pulse-orange">🧠</span><span class="xr-hud-val xr-hud-val-orange xr-hud-pulse-orange">AI THINKING... (${Math.round(queryDuration / 1000)}s)</span>`;
            }
        } else {
            thinkingEl.style.display = 'none';
        }
    }

    // 4. Live Dev Feed Fetching (throttle to every 3000ms)
    const now = Date.now();
    if (now - lastDevFeedFetchTime > 3000) {
        lastDevFeedFetchTime = now;
        fetch('/dev_feed.json')
            .then(r => r.json())
            .then(data => {
                const feedValEl = document.getElementById('xr-hud-dev-feed-val');
                const feedPanelEl = document.getElementById('xr-hud-dev-feed');
                if (feedValEl && data && data.status) {
                    feedValEl.textContent = `DEV FEED: ${data.status.toUpperCase()}`;
                    if (feedPanelEl) {
                        if (data.status.toLowerCase().includes('fail') || data.status.toLowerCase().includes('error')) {
                            feedPanelEl.className = 'xr-hud-panel xr-hud-panel-red-flash';
                            feedValEl.className = 'xr-hud-val xr-hud-val-red';
                        } else if (data.status.toLowerCase().includes('success') || data.status.toLowerCase().includes('complete') || data.status.toLowerCase().includes('done')) {
                            feedPanelEl.className = 'xr-hud-panel xr-hud-panel-green';
                            feedValEl.className = 'xr-hud-val xr-hud-val-green';
                        } else if (data.status.toLowerCase().includes('modify') || data.status.toLowerCase().includes('compil') || data.status.toLowerCase().includes('run')) {
                            feedPanelEl.className = 'xr-hud-panel xr-hud-panel-cyan xr-hud-pulse-orange'; // animate active edits
                            feedValEl.className = 'xr-hud-val xr-hud-val-cyan';
                        } else {
                            feedPanelEl.className = 'xr-hud-panel xr-hud-panel-cyan';
                            feedValEl.className = 'xr-hud-val xr-hud-val-cyan';
                        }
                    }
                }
            })
            .catch(() => { });
    }

    // 5. Get Swarm status
    const swarmEl = document.getElementById('xr-hud-swarm');
    if (swarmEl) {
        const assets = '$11.45 USDT';
        swarmEl.innerHTML = `<span class="xr-hud-icon">🐝</span><span class="xr-hud-val xr-hud-val-pink">SWARM: 3 AGENTS | ${assets}</span>`;
    }

    // 6. Get Telemetry status
    const telemetryEl = document.getElementById('xr-hud-telemetry');
    if (telemetryEl) {
        const tData = (window as any).foveaiDashboard?.telemetryData || { CPU_PCT: 0, GPU_PCT: 0, RAM_PCT: 0 };
        const isSoulReachable = (window as any).foveaiBrainState?.soulReachable !== false;

        if (isSoulReachable) {
            telemetryEl.className = 'xr-hud-panel xr-hud-panel-green';
            telemetryEl.innerHTML = `<span class="xr-hud-icon">🖥️</span><span class="xr-hud-val xr-hud-val-green">SOUL: ONLINE | CPU: ${Math.round(tData.CPU_PCT)}% | GPU: ${Math.round(tData.GPU_PCT)}%</span>`;
        } else {
            telemetryEl.className = 'xr-hud-panel xr-hud-panel-orange';
            telemetryEl.innerHTML = `<span class="xr-hud-icon">⚠️</span><span class="xr-hud-val xr-hud-val-orange">LOCAL SOUL UNAVAILABLE (CLOUD MODE)</span>`;
        }
    }

    if ((window as any).xr3dHudMesh) {
        try {
            ((window as any).xr3dHudMesh.material as any).map.update();
        } catch (e) { }
    }
}

// Window listener for VR 3D HUD toggle
window.addEventListener('foveai_3d_hud_toggle', (e: any) => {
    const enabled = e.detail.enabled;
    const hudMesh = (window as any).xr3dHudMesh;
    if (hudMesh) {
        hudMesh.visible = enabled;
    }
    const peripheralMesh = (window as any).xrPeripheralHudMesh;
    if (peripheralMesh) {
        peripheralMesh.visible = enabled;
    }
});

// Window listeners for XR-IDE video wall playing & stopping
window.addEventListener('xr_ide_play_video', (e: any) => {
    const url = e.detail?.url;
    if (url && xrIdeHud) {
        xrIdeHud.playVideo(url);
    }
});

window.addEventListener('xr_ide_stop_video', () => {
    if (xrIdeHud) {
        xrIdeHud.stopVideo();
    }
});

// Dashboard placement strategy:
// - Quest (unit=qu/q3): keep in document.body at left:-10000px so the SVG snapshot
//   hit-test works. The 3D holographic panel is the ONLY UI in XR — no dom-overlay.
// - Desktop / non-Quest: move into xrOverlay so it appears as a 2D layer in XR.
const _isQuestUnit = contextManager.getUnit() === 'qu' || contextManager.getUnit() === 'q3';
if (dashboard?.getElement()) {
    if (_isQuestUnit) {
        // Leave dashboard in document.body — CSS already positions it at left:-10000px.
        // Just do the initial tab navigation.
        const initialTab = contextManager.getInitialTab();
        if (initialTab && initialTab !== 'cognition') {
            dashboard.setActiveTab(initialTab);
        }
    } else {
        xrOverlay.appendChild(dashboard.getElement());
        const initialTab = contextManager.getInitialTab();
        if (initialTab && initialTab !== 'cognition') {
            dashboard.setActiveTab(initialTab);
        }
    }
}

// VideoChat goes into the overlay on non-Quest only (Quest uses 3D panel for all UI)
if (videoChat?.getElement() && !_isQuestUnit) {
    xrOverlay.appendChild(videoChat.getElement());
}

// Initialize user virtual representation on Layer 1
initUserAvatar();

(window as any).avatarManager = avatar;

// --- XR HANDSHAKE ---
async function startXRSession(mode: 'vr' | 'ar' = 'ar') {
    if (!env) {
        dashboard.log('XR Error: Environment not initialized', '#ff007f');
        return;
    }

    if (contextManager.getUnit() === 'qu' || contextManager.getUnit() === 'q3') {
        env.renderer.domElement.style.display = 'block';
    }

    if (!navigator.xr) {
        dashboard.log('XR Error: WebXR API not available — cannot start session', '#ff007f');
        return;
    }

    // Reset clock to avoid large delta spike on first XR frame
    clock.start();
    clock.getDelta(); // Discard accumulated time

    dashboard.log(`Initiating Immersive ${mode.toUpperCase()} (${(window as any).LINK_REVISION})...`, 'var(--neon-blue)');

    // Pre-request microphone access during the user gesture — Quest 3 will exit
    // immersive mode if getUserMedia is called inside the XR session
    try {
        // Inherit the anchored microphone stream from the outer 2D world if available
        if ((window as any).foveaiAnchoredMicStream) {
            cachedMicStream = (window as any).foveaiAnchoredMicStream;
            dashboard.log('Microphone successfully teleported from outer 2D anchor', '#39ff14');
        }
        // NOTE: We moved the fallback getUserMedia call to AFTER requestSession.
        // Awaiting getUserMedia here destroys the synchronous 'transient user gesture' context,
        // causing requestSession to fail with a SecurityError!

        // Pre-create and resume the shared global AudioContext under this user gesture!
        const AudioContextClass = (window as any).AudioContext || (window as any).webkitAudioContext;
        if (AudioContextClass) {
            if (!(window as any).foveaiAudioContext) {
                (window as any).foveaiAudioContext = new AudioContextClass();
            }
            const gCtx = (window as any).foveaiAudioContext as AudioContext;
            if (gCtx.state === 'suspended') {
                // DO NOT AWAIT THIS! Awaiting destroys the transient user activation needed for requestSession!
                gCtx.resume().then(() => dashboard.log('Shared AudioContext pre-resumed for XR', '#39ff14')).catch(e => console.warn(e));
            }
        }
    } catch (micErr) {
        dashboard.log(`Mic/Audio pre-request failed: ${micErr} -- Push-to-Talk may not work`, '#ffaa00');
    }

    // Log avatar state before entering XR
    const avatarLoaded = !!(avatar && avatar.vrm);
    const avatarScene = avatar?.vrm ? 'in scene' : 'NOT in scene';
    dashboard.log(`XR Pre-check: avatar=${avatarLoaded} (${avatarScene}), camera=(${env.camera.position.x.toFixed(2)}, ${env.camera.position.y.toFixed(2)}, ${env.camera.position.z.toFixed(2)})`, 'var(--neon-blue)');

    const sessionType = mode === 'ar' ? 'immersive-ar' : 'immersive-vr';
    const xrOptions: any = {
        optionalFeatures: ['local-floor', 'hand-tracking', 'layers', 'plane-detection', 'mesh-detection'],
    };
    // dom-overlay now only contains lightweight HUD indicators (hub, recording dot, flash, audio prompt).
    // The full dashboard is NOT in the overlay on Quest — it stays in document.body at left:-10000px.
    // So enabling dom-overlay on Quest is safe and required for the XR indicator hub to be visible.
    const overlayRoot = document.getElementById('xr-dom-overlay');
    if (overlayRoot) {
        xrOptions.optionalFeatures.push('dom-overlay');
        xrOptions.domOverlay = { root: overlayRoot };
    }

    try {
        // We CANNOT await navigator.xr.isSessionSupported here, because any await destroys the transient user gesture!
        // Instead, we directly request the session and rely on the catch block if it fails.
        let session;
        try {
            session = await (navigator as any).xr.requestSession(sessionType, xrOptions);
        } catch (e: any) {
            dashboard.log(`XR: ${sessionType} failed: ${e.message}`, '#ffaa00');
            if (mode === 'ar') {
                dashboard.log('XR: AR not available -- trying VR fallback...', 'var(--neon-pink)');
                // We cannot start VR fallback in the same click handler because the gesture is now consumed by the rejection!
                // But we will try anyway.
                startXRSession('vr');
            } else {
                dashboard.log('XR: No immersive mode available -- desktop mode', '#ffaa00');
            }
            return;
        }
        (window as any).xrSession = session;
        env.renderer.xr.enabled = true;
        env.renderer.xr.setSession(session);

        // Request high-resolution supersampled rendering (1.75x) for extremely crisp text/avatar details,
        // and foveation level 1.0 to keep performance butter-smooth on Quest 3 hardware
        try {
            env.renderer.xr.setFramebufferScaleFactor(1.75);
            env.renderer.xr.setFoveation(1.0);
            dashboard.log('[XR] HD Supersampling (1.75x) & Foveation (1.0) active', 'var(--neon-green)');
        } catch (e) {
            console.warn('[XR] Failed to configure WebXR foveation/scale factor:', e);
        }

        env.setImmersiveMode(mode);

        // Hide Layer 1 objects (user avatar cylinder, mirror portal) from the user's XR camera
        // so they don't see their own virtual body representation
        env.camera.layers.disable(1);

        // Force environment blend mode request for VR fallback sessions (PCVR/Meta Link)
        // to enable camera passthrough blending on transparent backgrounds
        if (session.requestBlendMode) {
            session.requestBlendMode('alpha-blend')
                .then(() => console.log('[XR] Environment blend mode set to alpha-blend (Passthrough).'))
                .catch((e: any) => {
                    console.warn('[XR] Failed to requestBlendMode alpha-blend:', e);
                    session.requestBlendMode('additive')
                        .then(() => console.log('[XR] Environment blend mode set to additive.'))
                        .catch((_e: any) => { });
                });
        }

        // The Oculus Browser silences flat-page media streams upon entering immersive WebXR mode!
        // We must release the old stream and request a new one INSIDE the immersive context.
        if (cachedMicStream && (cachedMicStream as any) !== "denied") {
            dashboard.log('XR: Releasing flat-page mic stream...', '#00f3ff');
            cachedMicStream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
        }

        if ((cachedMicStream as any) !== "denied") {
            dashboard.log('XR: Requesting Immersive Microphone access...', 'var(--neon-blue)');
            try {
                cachedMicStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
                (window as any).foveaiCachedMicStream = cachedMicStream;
                dashboard.log('Immersive Microphone access granted!', '#39ff14');

                // WORKAROUND: Keep mic stream active/alive in Chromium/Android/Oculus Browser
                const aud = new Audio();
                aud.srcObject = cachedMicStream;
                aud.muted = true;
                aud.play().catch(e => console.warn('[XR] Workaround audio play failed:', e));
                (window as any).foveaiWorkaroundAudio = aud;
            } catch (err: any) {
                dashboard.log(`XR Mic access denied: ${err.message}`, '#ffaa00');
            }
        }

        // The successfully acquired microphone stream is cached globally and accessed by the VAD system.
        if (cachedMicStream && (cachedMicStream as any) !== "denied") {
            dashboard.log('[XR] Active microphone stream ready for voice system', '#39ff14');

            // Restart the voice system on the new immersive mic stream
            const dashInstance = (window as any).dashboard || (window as any).foveaiDashboard;
            if (dashInstance && typeof dashInstance.stopListening === 'function' && typeof dashInstance.startListening === 'function') {
                try {
                    dashInstance.stopListening(true);
                    // Give it a brief delay to cleanly shutdown old nodes before re-initializing
                    setTimeout(() => {
                        dashInstance.startListening();
                        dashboard.log('[XR] Voice detection successfully restarted on immersive mic.', '#39ff14');
                    }, 300);
                } catch (err) {
                    console.warn('[XR] Failed to restart VAD on immersive mic:', err);
                }
            }
        }

        // Log Left Menu Button interception warnings to educate user
        dashboard.log('[XR] Note: Left Menu button (index 3) is reserved by Quest OS/Oculus Browser.', 'var(--neon-pink)');
        dashboard.log('[XR] Toggle the holographic HUD strictly using Left Controller Face Button [X] (index 4).', 'var(--neon-pink)');

        // Dynamically add XR classes to body and dashboard to trigger VR floating layouts!
        document.body.classList.remove('mode-web', 'mode-desktop', 'mode-mobile');
        document.body.classList.add('mode-xr', 'unit-vr');

        const dashEl = dashboard?.getElement();
        if (dashEl) {
            dashEl.classList.remove('mode-web', 'mode-desktop', 'mode-mobile');
            dashEl.classList.add('mode-xr');
        }

        // Start closed in XR by default (completely hidden off-screen to preserve VR immersion)
        if (dashboard) {
            dashboard.toggle(false);
        }

        // Hide IDE HUD when entering XR
        if (xrIdeHud) {
            xrIdeHud.setVisible(false);
        }

        // Start overlay pointer events as none when closed, so clicks can pass through to the 3D scene
        xrOverlay.style.pointerEvents = 'none';

        // Disable 2D inputs and select dropdowns in VR to prevent virtual keyboard or system dropdown popups from kicking you out of WebXR
        const interactiveInputs = document.querySelectorAll('#foveai-dashboard input, #foveai-dashboard textarea, #foveai-dashboard select');
        interactiveInputs.forEach((el: any) => {
            el.disabled = true;
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                el.placeholder = "Disabled in VR (speak using B button VAD)";
            }
        });

        dashboard.log(`${mode.toUpperCase()} session started successfully`, '#39ff14');
        dashboard.log(`XR Session: mode=${mode}, inputSources=${session.inputSources ? session.inputSources.length : 0}`, 'var(--neon-blue)');

        // Initialize Quest headset screen/camera capture stream
        const composite = getCompositeVision();
        if (composite) {
            composite.initPassthrough().then(success => {
                if (success) {
                    dashboard.log('📹 Quest passthrough stream successfully initialized for capture', 'var(--neon-green)');
                } else {
                    dashboard.log('⚠️ Quest passthrough stream initialization failed or skipped', 'var(--neon-orange)');
                }
            }).catch(e => console.warn(e));
        }

        // Unlock audio pipeline during user gesture — Quest 3 requires this
        audio.unlockAudio();
        dashboard.log('Audio pipeline unlocked for XR', 'var(--neon-blue)');

        // Trigger VAD listening automatically 1000ms after session starts, using pre-cached stream
        setTimeout(() => {
            if ((window as any).xrSession && cachedMicStream) {
                dashboard.log('[XR] Auto-activating Voice Activity Detection (VAD)...', 'var(--neon-green)');
                userWantsVad = true;
                dashboard.startListening();
            }
        }, 1000);

        // Ensure avatar is visible in XR — reset position and scale
        if (avatar && avatar.vrm) {
            // Verify VRM scene is actually in the scene graph
            if (!env.scene.children.includes(avatar.vrm.scene)) {
                dashboard.log('XR: VRM scene was NOT in scene graph — re-adding', '#ff007f');
                env.scene.add(avatar.vrm.scene);
            }
            avatar.setPosition(0, 0.0, -2.0);
            avatar.vrm.scene.rotation.y = Math.PI;
            avatar.vrm.scene.scale.set(1, 1, 1);
            avatar.vrm.scene.visible = true;
            dashboard.log('Avatar repositioned for XR session', 'var(--neon-blue)');
        } else if (avatar) {
            dashboard.log('Avatar not loaded — attempting nuclear reset for XR...', 'var(--neon-pink)');
            try {
                await avatar.nuclearReset();
                if (avatar.vrm) {
                    if (!env.scene.children.includes(avatar.vrm.scene)) {
                        env.scene.add(avatar.vrm.scene);
                    }
                    avatar.setPosition(0, 0.0, -2.0);
                    avatar.vrm.scene.rotation.y = Math.PI;
                    avatar.vrm.scene.scale.set(1, 1, 1);
                    avatar.vrm.scene.visible = true;
                    dashboard.log('Avatar reset and repositioned for XR', '#39ff14');
                }
            } catch (resetErr) {
                dashboard.log(`Avatar reset failed: ${resetErr}`, '#ff007f');
            }
        }

        // Log when controllers connect/disconnect (diagnostic for inputSources=0)
        session.addEventListener('inputsourceschange', (event: any) => {
            const count = session.inputSources.length;
            const statusEl = document.getElementById('xr-controller-status');
            if (statusEl) {
                const hands = Array.from(session.inputSources).map((s: any) => s.handedness?.charAt(0).toUpperCase() || '?').join('+');
                statusEl.innerHTML = `<span>PAD</span>🎮 ${count} ${count > 0 ? `(${hands})` : ''}`;
                statusEl.style.borderColor = count >= 2 ? 'var(--neon-green)' : count >= 1 ? '#ffaa00' : 'var(--neon-pink)';
            }
            dashboard.log(`[XR] Input sources changed: ${count} controller(s)`, 'var(--neon-blue)');
            for (const src of session.inputSources) {
                const btnCount = src.gamepad?.buttons?.length ?? 0;
                const axesCount = src.gamepad?.axes?.length ?? 0;
                dashboard.log(`  → ${src.handedness} (profiles: ${src.profiles?.join(', ') || 'unknown'}, buttons: ${btnCount}, axes: ${axesCount})`, 'var(--neon-blue)');
            }
        });

        session.addEventListener('end', () => {
            dashboard.log('XR session ended -- returning to desktop', '#ffaa00');
            env.setImmersiveMode('desktop');
            (window as any).xrSession = null;

            if (contextManager.getUnit() === 'qu' || contextManager.getUnit() === 'q3') {
                // Quest mode: blank the page immediately, then close the tab.
                // window.close() alone is blocked by browsers when the user typed the URL.
                // Redirecting to about:blank first gives an instant black screen;
                // close() fires in the next tick and works on Oculus Browser.
                if (env) env.renderer.domElement.style.display = 'none';
                document.body.innerHTML = '';
                document.body.style.background = '#000';
                setTimeout(() => {
                    try { window.close(); } catch (_) { }
                    // Last resort: navigate away so the XR UI is never seen
                    try { window.location.replace('about:blank'); } catch (_) { }
                }, 50);
                return; // Skip the rest of the cleanup — page is being destroyed
            }

            // Hide holographic menu panel and helper meshes
            if (holographicPanelMesh) {
                holographicPanelMesh.visible = false;
                if (xrIdeHud) xrIdeHud.setVisible(false);
            }
            const xr3dHudMesh = (window as any).xr3dHudMesh;
            if (xr3dHudMesh) {
                xr3dHudMesh.visible = false;
                if (xr3dHudMesh.parent) {
                    xr3dHudMesh.parent.remove(xr3dHudMesh);
                }
            }
            if (laserBeam) (laserBeam.material as THREE.LineBasicMaterial).opacity = 0.0;
            if (laserBeamRight) (laserBeamRight.material as THREE.LineBasicMaterial).opacity = 0.0;
            if (holographicCursorMesh) holographicCursorMesh.visible = false;
            if (holographicCursorRight) holographicCursorRight.visible = false;
            showVirtualKeyboard = false;
            holographicInputText = '';

            // Restore default classes
            document.body.classList.remove('mode-xr', 'unit-vr');
            document.body.classList.add(`mode-${contextManager.getMode()}`);

            const dashEl = dashboard?.getElement();
            if (dashEl) {
                dashEl.classList.remove('mode-xr');
                dashEl.classList.add(`mode-${contextManager.getMode()}`);
                // Re-expand dashboard automatically on desktop exit if it was standard web mode
                if (contextManager.getMode() === 'web') {
                    dashboard.toggle(true);
                }
            }

            // Restore overlay pointer events to none so desktop click-drag works on standard WebGL canvas
            xrOverlay.style.pointerEvents = 'none';
            if (avatar) {
                avatar.setPosition(0, -0.8, -2.0);
                avatar.isCrouching = false;
                avatar.steeringActive = false;
            }
            hapticsWandMode = false;
            if (wandLeft) wandLeft.setActive(false);
            if (wandRight) wandRight.setActive(false);

            // Restore desktop/2D inputs
            const interactiveInputs = document.querySelectorAll('#foveai-dashboard input, #foveai-dashboard textarea, #foveai-dashboard select');
            interactiveInputs.forEach((el: any) => {
                el.disabled = false;
                if (el.tagName === 'INPUT') {
                    const id = el.getAttribute('id');
                    if (id === 'chrono-tag') el.placeholder = "UI, SOUL, XR...";
                    else if (id === 'chrono-title') el.placeholder = "Short headline...";
                    else el.placeholder = "Type a message...";
                } else if (el.tagName === 'TEXTAREA') {
                    el.placeholder = "Details...";
                }
            });

            // Hide XR overlay indicators
            const recIndicator = document.getElementById('xr-recording-indicator');
            if (recIndicator) recIndicator.style.display = 'none';
            // Release cached mic stream when leaving XR
            if (cachedMicStream) {
                cachedMicStream.getTracks().forEach(t => t.stop());
                cachedMicStream = null;
            }
        });

    } catch (e: any) {
        dashboard.log(`${mode.toUpperCase()} Error: ${e.message}`, '#ff007f');
        if (mode === 'ar') {
            dashboard.log('AR/XR failed, trying VR mode...', 'var(--neon-pink)');
            startXRSession('vr');
        } else {
            dashboard.log('XR/VR fallback exhausted. Using desktop mode.', '#ffaa00');
        }
    }
}

// Default to AR/XR mode - VR is fallback
window.addEventListener('foveai_request_vr', () => startXRSession('vr'));

let desktopScreenMesh: THREE.Mesh | null = null;
window.addEventListener('foveai_start_desktop_stream', async () => {
    try {
        dashboard.log('[XR] Requesting Desktop Screen Share...', 'var(--neon-blue)');
        const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        const video = document.createElement('video');
        video.srcObject = stream;
        video.play();

        const desktopTexture = new THREE.VideoTexture(video);
        desktopTexture.colorSpace = THREE.SRGBColorSpace;

        if (desktopScreenMesh && env) {
            env.scene.remove(desktopScreenMesh);
        }

        // Huge 16:9 aspect ratio screen (e.g., 3.2m x 1.8m)
        const geo = new THREE.PlaneGeometry(3.2, 1.8);
        const mat = new THREE.MeshBasicMaterial({ map: desktopTexture, side: THREE.DoubleSide });

        desktopScreenMesh = new THREE.Mesh(geo, mat);

        // Put the desktop screen share exclusively on Layer 1!
        // This makes it invisible to the user's eyes (preventing overlapping with Quest OS browser windows),
        // but fully visible to Jen's viewport head cameras.
        desktopScreenMesh.layers.set(1);
        desktopScreenMesh.traverse((child) => child.layers.set(1));

        if (env) {
            // Position the virtual screen exactly 1.5 meters in front of Jen's avatar head position facing her
            if (avatar && avatar.vrm) {
                const avatarPos = new THREE.Vector3();
                const headBone = avatar.vrm.humanoid?.getNormalizedBoneNode('head');
                if (headBone) {
                    headBone.getWorldPosition(avatarPos);
                } else {
                    avatarPos.copy(avatar.vrm.scene.position);
                    avatarPos.y += 1.3;
                }

                const avatarForward = new THREE.Vector3(0, 0, -1).applyQuaternion(avatar.vrm.scene.quaternion);
                avatarForward.y = 0;
                if (avatarForward.lengthSq() > 0.001) {
                    avatarForward.normalize();
                } else {
                    avatarForward.set(0, 0, -1);
                }

                desktopScreenMesh.position.copy(avatarPos).addScaledVector(avatarForward, 1.5);
                desktopScreenMesh.lookAt(avatarPos);
            } else {
                // Fallback: Position the virtual screen 1.8 meters in front of the user's headset view direction
                const userPos = new THREE.Vector3();
                const userQuat = new THREE.Quaternion();
                env.camera.getWorldPosition(userPos);
                env.camera.getWorldQuaternion(userQuat);

                const forwardVec = new THREE.Vector3(0, 0, -1).applyQuaternion(userQuat);
                desktopScreenMesh.position.copy(userPos).addScaledVector(forwardVec, 1.8);
                desktopScreenMesh.lookAt(userPos);
            }

            env.scene.add(desktopScreenMesh);
        }
        dashboard.log('[XR] Desktop Stream mirrored on Layer 1 (Jen-only view).', '#39ff14');

    } catch (e) {
        dashboard.log(`[XR] Desktop Stream failed: ${e}`, '#ff007f');
    }
});

window.addEventListener('foveai_toggle_immersive', (e: any) => {
    const mode = e.detail || 'ar';
    dashboard.log(`Starting ${mode.toUpperCase()} session...`, 'var(--neon-blue)');
    if ((window as any).xrSession) {
        (window as any).xrSession.end().then(() => startXRSession(mode));
    } else {
        startXRSession(mode);
    }
});

// Continuous VAD Voice Dialogue: Auto-resume listening when Jen finishes speaking in XR mode
window.addEventListener('foveai_tts_ended', () => {
    if ((window as any).xrSession && userWantsVad) {
        dashboard.log('[XR] Continuous Dialogue: Auto-resuming Voice Activity Detection (VAD) after speech ended...', 'var(--neon-green)');
        // Short delay to avoid clipping active audio trails
        setTimeout(() => {
            if ((window as any).xrSession && userWantsVad) {
                dashboard.startListening();
            }
        }, 600);
    }
});

// Code Agency: Listen for <code:...> bracket tokens from LLM, execute via CodeAgency, dispatch results
const codeAgency = new CodeAgency((msg, color) => dashboard.log(`[CodeAgency] ${msg}`, color));
window.addEventListener('foveai_code_action', (async (e: CustomEvent) => {
    const detail = e.detail;
    const action = detail.action || '';
    const params = detail.params || {};
    const fullMatch = detail.fullMatch || '';
    dashboard.log(`[CodeAgency] Executing <code:${action}>`, '#00f3ff');
    try {
        if (action === 'search') {
            const query = params.query || params.q || fullMatch.replace(/<code:search\s*/, '').replace(/>$/, '').trim() || '';
            const results = await codeAgency.searchCode(query);
            window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                detail: { action: 'search', success: true, query, results }
            }));
        } else if (action === 'read') {
            const path = params.path || params.file || fullMatch.replace(/<code:read\s*/, '').replace(/>$/, '').trim() || '';
            const content = await codeAgency.readFile(path);
            window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                detail: { action: 'read', success: !!content, path, content: content || '' }
            }));
        } else if (action === 'exec') {
            const cmd = params.command || params.cmd || fullMatch.replace(/<code:exec\s*/, '').replace(/>$/, '').trim() || '';
            const result = await codeAgency.exec(cmd);
            window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                detail: { action: 'exec', success: result.success, message: result.message }
            }));
        } else if (action === 'write') {
            const path = params.path || '';
            const content = params.content || '';
            const result = await codeAgency.writeFile(path, content);
            window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                detail: { action: 'write', success: result.success, path, message: result.message }
            }));
        } else if (action === 'git_status') {
            const status = await codeAgency.gitStatus();
            window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                detail: { action: 'git_status', success: true, status }
            }));
        } else if (action === 'list_dir') {
            const dir = params.dir || params.path || fullMatch.replace(/<code:list_dir\s*/, '').replace(/>$/, '').trim() || '.';
            const files = await codeAgency.listDir(dir);
            window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                detail: { action: 'list_dir', success: true, dir, files }
            }));
        } else {
            dashboard.log(`[CodeAgency] Unknown action: ${action}`, '#ffaa00');
        }
    } catch (err: any) {
        dashboard.log(`[CodeAgency] Error: ${err.message}`, '#ff007f');
        window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
            detail: { action, success: false, message: err.message }
        }));
    }
}) as unknown as EventListener);

// Code Agency Results: Display code search/read/exec results in the chat
window.addEventListener('foveai_code_action_result', ((e: CustomEvent) => {
    const detail = e.detail;
    const action = detail.action || 'unknown';
    if (detail.success) {
        if (action === 'search') {
            const results = detail.results || [];
            const summary = results.length > 0
                ? results.slice(0, 5).map((r: any) => `  📄 ${r.file}:${r.line} — ${r.content.substring(0, 80)}`).join('\n')
                : '  No results found.';
            const more = results.length > 5 ? `\n  ... and ${results.length - 5} more` : '';
            dashboard.addMessage('system', `🔍 Code search "${detail.query}":\n${summary}${more}`);
        } else if (action === 'read') {
            const content = detail.content || '';
            const lines = content.split('\n').length;
            const preview = content.substring(0, 500);
            dashboard.addMessage('system', `📖 Read ${detail.path} (${lines} lines):\n\`\`\`\n${preview}\n\`\`\``);
        } else if (action === 'exec') {
            dashboard.addMessage('system', `⚡ Exec: ${detail.message || 'OK'}`);
        } else if (action === 'write') {
            dashboard.addMessage('system', `📝 Written to ${detail.path}: ${detail.message || 'OK'}`);
        } else if (action === 'git_status') {
            dashboard.addMessage('system', `📊 Git: ${detail.status}`);
        } else if (action === 'list_dir') {
            const files = detail.files || [];
            const listing = files.slice(0, 10).map((f: any) => `  ${f.isDir ? '📁' : '📄'} ${f.path || f.name}`).join('\n');
            const more = files.length > 10 ? `\n  ... and ${files.length - 10} more` : '';
            dashboard.addMessage('system', `📁 ${detail.dir}:\n${listing}${more}`);
        }
    } else {
        dashboard.addMessage('system', `⚠️ Code action "${action}" failed: ${detail.message || 'Unknown error'}`);
    }
}) as unknown as EventListener);

// Sync WebXR DOM overlay pointer events dynamically when the dashboard collapses or expands
window.addEventListener('foveai_dashboard_toggled', (e: any) => {
    const isExpanded = e.detail;
    if ((window as any).xrSession) {
        xrOverlay.style.pointerEvents = isExpanded ? 'auto' : 'none';
        dashboard.log(`[XR] Dashboard: pointerEvents = ${xrOverlay.style.pointerEvents}`, 'var(--neon-blue)');
    }
});

// Lazy-load LocalBrain — the heaviest dependency (@mlc-ai/web-llm) is code-split
let localBrainInstance: any = null;

// --- BRAIN STATE TRACKER (diagnostic) ---
(window as any).foveaiBrainState = {
    status: 'uninitialized',
    error: null as string | null,
    lastResponse: null as string | null,
    lastResponseTime: 0,
    initStart: 0,
    initEnd: 0,
    webGPU: 'unknown',
    fallbackUsed: null as string | null,
    cloudSlotUsed: null as string | null,
    soulReachable: null as boolean | null,
    directCloudReachable: null as boolean | null,
    budgetExhausted: false,
    privacyMode: false,
    lastCloudError: null as string | null,
};

async function getLocalBrain() {
    if (!localBrainInstance) {
        const { localBrain } = await import('./network/LocalBrain');
        localBrainInstance = localBrain;
    }
    return localBrainInstance;
}

/**
 * Soul service fallback — routes through the backend which can use
 * ollama_cloud / any configured cloud slot. Used when the local WebLLM
 * brain is non-functional or returns broken output.
 * Uses /api/proxy/soul/compagent (300s timeout, no auth gate).
 */
// --- SOUL FAILURE COOLDOWN ---
// When Soul Proxy fails, skip it for 60 seconds to avoid wasting time on dead endpoints
let _soulFailureTime = 0;
const SOUL_FAILURE_COOLDOWN_MS = 60_000;

// --- CLOUD FAILURE COOLDOWN ---
// If Direct Cloud fails (e.g. rate limit), block it for 1 hour to prevent spamming
let _cloudFailureTime = 0;
const CLOUD_FAILURE_COOLDOWN_MS = 3600_000;

let systemFeedbackQueue: string[] = [];

let fetchSoulPromise: Promise<any> = Promise.resolve();

async function fetchSoulFallback(message: string, context: string, deepThought: boolean = false, privacyMode: boolean = false, attachments: any[] = []): Promise<string | null> {
    const currentQueue = fetchSoulPromise;
    let resolveTask!: () => void;
    fetchSoulPromise = new Promise<void>(resolve => { resolveTask = resolve; });

    await currentQueue.catch(() => {});

    isBrainThinking = true;
    lastBrainQueryStartTime = Date.now();
    updateXRIndicatorHub();
    try {
        const spatialEnv = (window as any).spatialEnvironment;
        const spatialDesc = spatialEnv ? '\n\n' + spatialEnv.getSpatialDescription() : '';
        let activeContext = context + spatialDesc;

        let activeAttachments = attachments;
        if (attachments.length === 0 && shouldInit3D && env) {
            try {
                const xrCamera = env.renderer.xr.enabled && env.renderer.xr.isPresenting ? env.renderer.xr.getCamera() : undefined;
                const vision = await captureVisionForLLM(env.renderer, env.scene, env.camera, xrCamera);
                if (vision && vision.base64) {
                    activeAttachments = [{
                        name: `auto_composite_${Date.now()}.jpg`,
                        type: 'image',
                        mediaType: 'image/jpeg',
                        base64: vision.base64
                    }];
                    if (vision.webcamBase64) {
                        activeAttachments.push({
                            name: `webcam_view_${Date.now()}.jpg`,
                            type: 'image',
                            mediaType: 'image/jpeg',
                            base64: vision.webcamBase64
                        });
                    }
                    if (vision.passthroughBase64) {
                        activeAttachments.push({
                            name: `quest_view_${Date.now()}.jpg`,
                            type: 'image',
                            mediaType: 'image/jpeg',
                            base64: vision.passthroughBase64
                        });
                    }
                    activeContext += '\n\n' + vision.metadata;
                }
            } catch (visionErr) {
                console.warn('[Vision] Auto-capture inside fetchSoulFallback failed:', visionErr);
            }
        }

        const soulRecentlyFailed = (Date.now() - _soulFailureTime) < SOUL_FAILURE_COOLDOWN_MS;
        const cloudRecentlyFailed = (Date.now() - _cloudFailureTime) < CLOUD_FAILURE_COOLDOWN_MS;

        // Check if we are in local mode based on the dashboard telemetry
        const telModel = (dashboard as any).telemetryModel || "";
        const isLocalMode = telModel.toLowerCase().includes("unsloth") || telModel.toLowerCase().includes("lmstudio") || telModel.toLowerCase().includes("local");

        const endpoints: { url: string, label: string }[] = [];

        if (isLocalMode) {
            // LOCAL MODE: Try Soul Proxy first, then Direct Cloud
            if (!soulRecentlyFailed) endpoints.push({ url: '/api/proxy/soul/compagent/stream', label: 'Soul Proxy' });
            else dashboard.log('Soul Proxy: skipping (recently failed, 60s cooldown)', '#ffaa00');

            if (!cloudRecentlyFailed) endpoints.push({ url: '/api/cloud/chat', label: 'Direct Cloud' });
            else dashboard.log('Direct Cloud: skipping (recently failed, 1 hour cooldown)', '#ffaa00');
        } else {
            // CLOUD MODE: Try Direct Cloud first, then Soul Proxy
            if (!cloudRecentlyFailed) endpoints.push({ url: '/api/cloud/chat', label: 'Direct Cloud' });
            else dashboard.log('Direct Cloud: skipping (recently failed, 1 hour cooldown)', '#ffaa00');

            if (!soulRecentlyFailed) endpoints.push({ url: '/api/proxy/soul/compagent/stream', label: 'Soul Proxy' });
            else dashboard.log('Soul Proxy: skipping (recently failed, 60s cooldown)', '#ffaa00');
        }

        for (const endpoint of endpoints) {
            try {
                dashboard.log(`Cloud -- trying ${endpoint.label}${deepThought ? ' ([BRN] Deep Thought)' : ''}${privacyMode ? ' ([PRV] Privacy)' : ''}...`, 'var(--neon-pink)');
                // AbortController timeout — Soul Proxy can take >30s on cold boot local prompt eval.
                // 120s for regular, 240s for deep thought.
                const controller = new AbortController();
                const timeoutMs = deepThought ? 600000 : 300000;
                const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
                // Removed: Per-message soundboard nudge was forcing unnatural usage.
                // Jen will now use bracket tokens intentionally based on system context.
                let reservoirs = (window as any).foveaiContextReservoirs || {};
                if (Object.keys(reservoirs).length === 0) {
                    try { const val = localStorage.getItem('foveai_context_reservoirs'); if (val) reservoirs = JSON.parse(val); } catch (e) { }
                }
                let abilityMap = (window as any).foveaiAbilityMap || {};
                if (Object.keys(abilityMap).length === 0) {
                    try { const val = localStorage.getItem('foveai_ability_map'); if (val) abilityMap = JSON.parse(val); } catch (e) { }
                }
                const response = await fetch(endpoint.url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: message,
                        system_context: activeContext + ((window as any).foveaiSoundboardContext ? '\n\n' + (window as any).foveaiSoundboardContext : ''),
                        source: 'vessel_fallback',
                        deep_thought: deepThought,
                        privacy: privacyMode,
                        attachments: activeAttachments,
                        context_reservoirs: reservoirs,
                        context_ability_map: abilityMap,
                        chat_log: (window as any).foveaiChatLog || []
                    }),
                    signal: controller.signal,
                });
                clearTimeout(timeoutId);
                if (response.ok) {
                    let reply: string | null = null;
                    let errorMsg: string | null = null;
                    let data: any = {};
                    
                    if (endpoint.url.includes('/stream') && response.body) {
                        const reader = response.body.getReader();
                        const decoder = new TextDecoder("utf-8");
                        let fullText = '';
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;
                            const chunk = decoder.decode(value, { stream: true });
                            const lines = chunk.split('\n');
                            for (const line of lines) {
                                if (line.startsWith('data: ')) {
                                    const dataStr = line.substring(6).trim();
                                    if (dataStr === '[DONE]' || dataStr === '') continue;
                                    try {
                                        const parsed = JSON.parse(dataStr);
                                        if (parsed.text) {
                                            fullText += parsed.text;
                                            window.dispatchEvent(new CustomEvent('foveai_thought_stream', { detail: { thought: fullText } }));
                                        }
                                    } catch (e) {}
                                }
                            }
                        }
                        // Extract actual spoken speech from thought blocks
                        reply = fullText;
                        const thoughtMatch = fullText.match(/<thought>([\s\S]*?)<\/thought>/);
                        if (thoughtMatch) {
                            reply = fullText.replace(/<thought>[\s\S]*?<\/thought>/g, '').trim();
                        }
                        data = { response: reply, inference_backend: 'local-stream' };
                    } else {
                        data = await response.json();
                        reply = data.response || data.text || data.message || data.content || null;
                        errorMsg = data.error || null;
                    }

                    if (errorMsg && !reply) {
                        dashboard.log(`${endpoint.label} error: ${errorMsg}`, '#ff007f');
                        if (errorMsg.includes('daily_budget_exhausted') || errorMsg.includes('429 rate limit')) {
                            dashboard.log(`${endpoint.label}: GenAI daily budget exhausted -- cloud calls blocked until midnight UTC`, '#ff007f');
                            (window as any).foveaiBrainState.budgetExhausted = true;
                        }
                        continue; // Try next endpoint
                    }
                    if (reply && !isBrokenBrainResponse(reply)) {
                        dashboard.log(`${endpoint.label} succeeded (backend: ${data.inference_backend || 'unknown'})`, '#39ff14');
                        (window as any).foveaiBrainState.fallbackUsed = endpoint.label;
                        (window as any).foveaiBrainState.cloudSlotUsed = data.inference_backend || null;
                        if (data.active_persona_id) {
                            (window as any).foveaiBrainState.activePersonaId = data.active_persona_id;
                        }
                        if (endpoint.label === 'Soul Proxy') {
                            (window as any).foveaiBrainState.soulReachable = true;
                            _soulFailureTime = 0; // Reset cooldown on success
                        }
                        if (endpoint.label === 'Direct Cloud') {
                            (window as any).foveaiBrainState.directCloudReachable = true;
                            _cloudFailureTime = 0; // Reset cooldown on success
                        }
                        return reply;
                    }
                    const errInfo = data.error || 'empty/broken response';
                    const rawPreview = JSON.stringify(data).substring(0, 300);
                    dashboard.log(`${endpoint.label} returned: ${errInfo}`, '#ffaa00');
                    dashboard.log(`${endpoint.label} raw: ${rawPreview}`, '#ffaa00');
                    if (endpoint.label === 'Direct Cloud') _cloudFailureTime = Date.now();
                } else {
                    let bodyPreview = '';
                    try { bodyPreview = (await response.text()).substring(0, 200); } catch (_) { }
                    dashboard.log(`${endpoint.label}: HTTP ${response.status} -- ${bodyPreview}`, '#ffaa00');
                    if (endpoint.label === 'Soul Proxy') (window as any).foveaiBrainState.soulReachable = false;
                    if (endpoint.label === 'Direct Cloud') {
                        (window as any).foveaiBrainState.directCloudReachable = false;
                        _cloudFailureTime = Date.now();
                    }
                }
            } catch (err) {
                dashboard.log(`${endpoint.label} failed: ${err}`, '#ffaa00');
                if (endpoint.label === 'Soul Proxy') {
                    (window as any).foveaiBrainState.soulReachable = false;
                    _soulFailureTime = Date.now();
                }
                if (endpoint.label === 'Direct Cloud') {
                    (window as any).foveaiBrainState.directCloudReachable = false;
                    _cloudFailureTime = Date.now();
                }
            }
        }
        // Both endpoints failed — store the reason for the fallback message
        const soulOk = (window as any).foveaiBrainState.soulReachable;
        const cloudOk = (window as any).foveaiBrainState.directCloudReachable;
        (window as any).foveaiBrainState.lastCloudError = !soulOk && !cloudOk
            ? 'Soul unreachable + no cloud slots responding'
            : !soulOk ? 'Soul unreachable, cloud slots empty/broken'
                : !cloudOk ? 'Cloud slots unreachable (check .env API keys)'
                    : 'All endpoints returned empty/broken responses';
        dashboard.log(`Cloud failed: ${(window as any).foveaiBrainState.lastCloudError}`, '#ff007f');
        return null;
    } finally {
        isBrainThinking = false;
        updateXRIndicatorHub();
        if (systemFeedbackQueue.length > 0) {
            const queuedMsgs = systemFeedbackQueue.join('\n');
            systemFeedbackQueue = [];
            setTimeout(() => {
                fetchSoulFallback(`[SYSTEM FEEDBACK] ${queuedMsgs}\n(You may briefly and naturally react to this out loud in character if you wish, or simply adapt your internal context.)`, "System Feedback", false, true).catch(console.error);
            }, 500);
        }
        resolveTask();
    }
}

dashboard.setOnSendMessage(async (text) => {
    // Immediately stop VAD listening (and discard microphone audio) and cancel any active companion speech when sending a message
    dashboard.stopListening(true);
    videoChat.cancelSpeech();
    dashboard.addMessage('user', text);
    const useDeepThought = dashboard.deepThought;
    if (useDeepThought) dashboard.log('[BRN] Deep Thought -- routing directly to cloud', 'var(--neon-pink)');
    try {
        if (useDeepThought) {
            // Deep Thought: bypass local brain, go straight to cloud reasoning model
            const soulReply = await fetchSoulFallback(text, "Deep Thought", true);
            if (soulReply) {
                dashboard.addMessage('assistant', soulReply);
                videoChat.speak(soulReply, () => {
                    dashboard.startListening();
                });
                return;
            }
            dashboard.addMessage('assistant', 'Deep Thought unavailable -- cloud slots not responding.');
            dashboard.startListening();
            return;
        }
        // Cloud-first: always use cloud inference (WebLLM disabled for RTX 4060 VRAM constraints)
        const brainState = (window as any).foveaiBrainState;
        const privacyMode = dashboard.privacyMode;
        const context = privacyMode ? "VR Vessel Privacy" : "VR Vessel Cloud";
        const telModel = (dashboard as any).telemetryModel || "";
        const isLocal = telModel.toLowerCase().includes("unsloth") || telModel.toLowerCase().includes("lmstudio") || telModel.toLowerCase().includes("local");
        if (isLocal) {
            dashboard.log(`Brain: local-first (${privacyMode ? '[PRV] privacy -> LM Studio' : '[LCL] normal -> LM Studio'})`, 'var(--neon-blue)');
        } else {
            dashboard.log(`Brain: cloud-first (${privacyMode ? '[PRV] privacy -> OpenRouter' : '[CLD] normal -> Ollama Cloud'})`, 'var(--neon-blue)');
        }
        const soulReply = await fetchSoulFallback(text, context, useDeepThought, privacyMode);
        if (soulReply) {
            // Parse bracket tokens BEFORE displaying — this dispatches <self:search "query"> etc.
            const parsed = BracketParser.parse(soulReply);
            dashboard.addMessage('assistant', parsed.cleanText);
            videoChat.speak(parsed.cleanText, () => {
                dashboard.startListening();
            });
            return;
        }
        const cloudErr = (window as any).foveaiBrainState.lastCloudError || 'All cloud endpoints unreachable';
        dashboard.addMessage('assistant', `⚠️ Cloud unavailable: ${cloudErr}. Check Diagnosis tab for details.`);
        dashboard.startListening();
    } catch (err) {
        dashboard.log(`Brain Error: ${err}`, "#ff007f");
        dashboard.startListening();
    }
});

// --- BOOT ---
async function boot() {
    if ((window as any).foveaiBootCount > 0) return;
    (window as any).foveaiBootCount++;

    try {
        dashboard.log('Omega: Loading Memory...');
        try {
            await localMemory.initialize();
            dashboard.log('Omega: Memory Ready', '#39ff14');
        } catch (err) {
            dashboard.log('Memory init warning: ' + (err as Error).message, '#ffaa00');
        }

        dashboard.log('Omega: Loading Soundboard...');
        try {
            await soundboardRegistry.preloadAll();
            dashboard.log(`Omega: Soundboard Ready (${soundboardRegistry.getAllTags().length} expressions)`, '#39ff14');
        } catch (err) {
            dashboard.log('Soundboard init warning: ' + (err as Error).message, '#ffaa00');
        }

        // Fetch soundboard sensory context for brain injection
        try {
            const sbResp = await fetch('/api/soundboard/context');
            if (sbResp.ok) {
                const sbData = await sbResp.json();
                const sbTags: string[] = sbData.tags || [];
                (window as any).foveaiSoundboardTags = sbTags;
                (window as any).foveaiSoundboardContext = condenseSoundboardContext(sbTags);
                dashboard.log(`Omega: Soundboard Context Loaded (${sbTags.length} tags, condensed imperative)`, 'var(--neon-blue)');
            }
        } catch (err) {
            dashboard.log('Soundboard context fetch warning: ' + (err as Error).message, '#ffaa00');
        }

        dashboard.log('Omega: Cognitive Mind Active');

        // Reset Soul persona to companion mode ('foveai') on startup to prevent carrying over heavy development/librarian context
        try {
            await fetch('/api/soul/update_soul', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ active_persona_id: 'foveai' })
            });
            dashboard.log('Omega: Soul Persona reset to companion mode (foveai)', '#39ff14');
        } catch (err) {
            console.warn('[Boot] Failed to reset soul persona:', err);
        }

        const brainState = (window as any).foveaiBrainState;
        brainState.status = 'cloud_only'; // Uses server-side dynamic routing
        brainState.initStart = Date.now();
        brainState.initEnd = Date.now();

        // WebLLM local brain DISABLED — RTX 4060 (8GB) cannot run a useful local LLM
        // while also handling VR rendering, Stable Audio, and torch synthesis.
        // Dynamic architecture: routes to LM Studio (local) or Ollama/OpenRouter (cloud) on the backend
        dashboard.log('Brain: Unified routing active (WebLLM skipped — GPU reserved for VR/audio)', 'var(--neon-blue)');
        dashboard.log('Brain: [LCL] Local -> LM Studio | [CLD] Cloud -> Ollama | [PRV] Privacy -> OpenRouter', 'var(--neon-blue)');

        // Boot-time cloud connectivity check — warns immediately if no slots configured
        try {
            const diagResp = await fetch('/api/brain/diagnostic');
            if (diagResp.ok) {
                const diagData = await diagResp.json();
                const slots = diagData.direct_cloud?.slots_eligible || [];
                const soulOk = diagData.soul?.reachable;
                if (slots.length === 0 && !soulOk) {
                    dashboard.log('⚠️ NO CLOUD SLOTS CONFIGURED — set FoveAI_REPERTOIRE_* vars in .env', '#ff007f');
                    (window as any).foveaiBrainState.lastCloudError = 'No cloud slots configured — check .env';
                } else {
                    const slotNames = slots.join(', ') || 'none';
                    dashboard.log(`Brain: Cloud slots [${slotNames}]${soulOk ? ' + Soul OK' : ' (Soul unreachable)'}`, soulOk ? '#39ff14' : '#ffaa00');
                }
                // Test first eligible slot with a tiny prompt
                const testResult = diagData.direct_cloud?.test_result;
                if (testResult) {
                    if (testResult.success) {
                        dashboard.log(`Brain: Cloud test OK (${testResult.slot}): "${(testResult.reply_preview || '').substring(0, 40)}"`, '#39ff14');
                    } else {
                        dashboard.log(`Brain: Cloud test FAILED (${testResult.slot}): ${testResult.error || 'unknown'}`, '#ff007f');
                        (window as any).foveaiBrainState.lastCloudError = `Cloud test failed: ${testResult.error || 'unknown'}`;
                    }
                }
            }
        } catch (diagErr) {
            dashboard.log(`Brain: Diagnostic unavailable (${diagErr})`, '#ffaa00');
        }

        if (avatar && env) {
            dashboard.log('Omega: Manifesting Physical...');
            try {
                await avatar.loadManifest('/Animations/animation_manifest.json');
                dashboard.log('Omega: Manifest Loaded', '#39ff14');
            } catch (err) {
                dashboard.log('Manifest load warning: ' + (err as Error).message, '#ffaa00');
            }

            try {
                // Avatar files to try (in priority order).
                // VRM/GLB models live in /avatars/ on the production build.
                const avatarFiles = [
                    '/avatars/alicechan.vrm',
                    '/avatars/SchoolUniform.vrm',
                    '/avatars/linda.glb',
                    '/avatars/avatar.vrm',
                    '/alicechan.vrm',
                    '/SchoolUniform.vrm',
                    '/linda.glb',
                    '/avatar.vrm'
                ];
                let vrm = null;
                let loadedFile = '';
                let lastError: any = null;

                // Pre-flight: check which files exist with a tiny byte-range request.
                // NEVER do a full GET here — that downloads the whole model twice.
                dashboard.log('Scanning avatar files...', 'var(--neon-blue)');
                const availableFiles: string[] = [];
                for (const file of avatarFiles) {
                    try {
                        const check = await fetch(file, { method: 'GET', headers: { Range: 'bytes=0-0' } });
                        if (check.ok || check.status === 200 || check.status === 206 || check.status === 304 || check.status === 405) {
                            availableFiles.push(file);
                            const size = Number(check.headers.get('content-length') || 0);
                            const sizeKB = size > 1 ? (size / 1024).toFixed(0) : '?';
                            dashboard.log(`  ✓ ${file} ready`, 'var(--neon-green)');
                        } else if (check.status !== 404) {
                            dashboard.log(`  ✗ ${file} — HTTP ${check.status}`, '#ffaa00');
                        }
                    } catch {
                        dashboard.log(`  ✗ ${file} — not reachable`, '#ff007f');
                    }
                }

                // Always include the default avatar even if the probe failed (HTTPS/proxy quirks).
                const defaultAvatar = '/avatars/alicechan.vrm';
                if (!availableFiles.includes(defaultAvatar) && !availableFiles.includes('/alicechan.vrm')) {
                    dashboard.log('  ↻ Adding default avatar regardless of probe result', 'var(--neon-blue)');
                    availableFiles.unshift('/avatars/alicechan.vrm');
                }

                // De-duplicate: only try the first alias that resolved for each model.
                const tried = new Set<string>();
                const uniqueFiles: string[] = [];
                for (const file of availableFiles) {
                    const base = file.split('/').pop()!.toLowerCase();
                    if (!tried.has(base)) {
                        tried.add(base);
                        uniqueFiles.push(file);
                    }
                }

                if (uniqueFiles.length === 0) {
                    dashboard.log('Omega: No avatar files found. Place .vrm/.glb files in frontend/XR_Vessel/public/avatars/', '#ff0000');
                }

                for (const file of uniqueFiles) {
                    try {
                        console.log(`[Main] Attempting to load avatar: ${file}`);
                        dashboard.log(`Loading: ${file}...`, 'var(--neon-blue)');
                        vrm = await avatar.loadAvatar(file, env.scene, (pct) => {
                            const overallProgress = 70 + (pct * 25);
                            dashboard.log(`Avatar Load: ${Math.floor(overallProgress)}%`);
                        });

                        if (vrm) {
                            loadedFile = file;
                            console.log(`[Main] Avatar loaded successfully: ${file}`);
                            break;
                        } else {
                            console.log(`[Main] Avatar load returned null for: ${file}`);
                            lastError = 'VRM data missing from GLTF';
                        }
                    } catch (err) {
                        console.log(`[Main] Error loading avatar ${file}:`, err);
                        lastError = err;
                    }
                }

                if (!vrm) {
                    dashboard.log('Omega: All avatar files failed to load.', '#ff0000');
                    if (lastError) {
                        dashboard.log(`Last error: ${lastError.message || lastError}`, '#ff007f');
                    }
                    dashboard.log('Tip: Ensure VRM files exist in frontend/XR_Vessel/public/avatars/', '#ffaa00');
                    dashboard.log('The vessel will continue without a 3D avatar. Chat and voice still work.', '#ffaa00');
                } else {
                    // Position avatar 2 metres in front of the user, feet on floor
                    // VRM origin is at feet, so Y=-0.8 places feet at floor level
                    vrm.scene.position.set(0, -0.8, -2.0);
                    dashboard.log(`Omega: ${loadedFile.split('/').pop()} Manifested.`, '#39ff14');
                }
            } catch (err) {
                dashboard.log('Avatar load warning: ' + (err as Error).message, '#ffaa00');
            }
        }

        dashboard.log('SYSTEM SOVEREIGN ACTIVE (100%).', "#39ff14");
        impulseManager.start();

        // Trigger AI Greeting (always via cloud or fast fallback — local brain might still be loading)
        setTimeout(async () => {
            dashboard.log('Generating initial greeting...', 'var(--neon-blue)');
            const greetingPrompt = "The user has just connected to the vessel. Say a brief, warm, one-sentence greeting to welcome them.";
            try {
                const soulGreeting = await fetchSoulFallback(greetingPrompt, "Greeting");
                const greetingText = soulGreeting || "Welcome aboard! My cognitive core is active and I'm ready whenever you are.";
                dashboard.addMessage('assistant', greetingText);
                if (greetingText.trim()) {
                    (window as any)._pendingGreeting = greetingText;
                    videoChat.speak(greetingText);
                    // If audio pipeline is already active, clear pending greeting to prevent
                    // double-speak when user interacts (unlock handler replays _pendingGreeting)
                    try {
                        const testCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
                        if (testCtx.state !== 'suspended') {
                            (window as any)._pendingGreeting = null;
                        }
                        testCtx.close();
                    } catch (_) { /* keep pending greeting for Quest 3 cold boot */ }
                }
                if (avatar) (window as any).foveaiAvatar?.playCategory('Happy');
            } catch (e) {
                console.warn('Greeting generation failed:', e);
                dashboard.addMessage('assistant', 'Welcome aboard. Neural link stabilising...');
            }
        }, 3000);

        // --- CONTEXT-AWARE MODE TWEAKS (OMEGA_085) ---
        if (contextManager.isHUD()) {
            // Hide dashboard for HUD mode
            dashboard.getElement().style.display = 'none';
            if (env) env.setHUDMode(true);

            dashboard.log('Sovereign HUD: Clinical Overlay Active.', 'var(--neon-blue)');

            // HUD Camera Position
            if (env) {
                env.camera.position.set(0, 1.15, 0.5);
                // controls is scoped to env check in constructor, so we need local access or just direct move
                // Since this is boot, we just move camera.
            }

            // Auto-start video chat in HUD mode
            setTimeout(async () => {
                if (avatar) {
                    await avatar.nuclearReset();
                    avatar.setZoom(true);
                }
                if ((window as any).foveaiVideoChat) {
                    (window as any).foveaiVideoChat.start();
                }
            }, 1000);
        }

        if (contextManager.isMobile()) {
            // Dashboard auto-expand for mobile
            setTimeout(() => dashboard.toggle(true), 500);
        }

    } catch (err: any) {
        dashboard.log(`BOOT FAULT: ${err.message}`, "#ff007f");
    }
}

// --- RENDER LOOP ---
const clock = new THREE.Clock();

function render(time: number, frame?: XRFrame) {
    if (!env) return;

    // Update native 3D UI
    ThreeMeshUI.update();

    // Force transparent clear alpha for WebXR sessions to override Three.js WebXRManager's 
    // default clearAlpha = 1.0 overrides when environmentBlendMode is 'opaque' (e.g. PCVR Meta Link),
    // allowing the compositor to overlay the transparent canvas onto the passthrough feed.
    if (env.renderer.xr.enabled && env.renderer.xr.isPresenting) {
        env.renderer.setClearAlpha(0.0);

        const xrCamera = env.renderer.xr.getCamera();
        if (xrCamera) {
            xrCamera.layers.disable(1);
            if (xrCamera.cameras) {
                xrCamera.cameras.forEach((cam: THREE.Camera) => {
                    cam.layers.disable(1);
                });
            }
        }
        const tempCamPos = new THREE.Vector3();
        const tempCamQuat = new THREE.Quaternion();
        xrCamera.getWorldPosition(tempCamPos);
        xrCamera.getWorldQuaternion(tempCamQuat);

        // --- WEBXR PLANE DETECTION (Scene Understanding) ---
        const currentTime = Date.now();
        if (frame && (window as any).spatialEnvironment && (currentTime - lastPlaneParseTime > 2000)) {
            lastPlaneParseTime = currentTime;
            const detectedPlanes = (frame as any).detectedPlanes;
            if (detectedPlanes && detectedPlanes.size > 0) {
                const referenceSpace = env.renderer.xr.getReferenceSpace();
                if (referenceSpace) {
                    const anchors: any[] = [];
                    let planeId = 0;
                    detectedPlanes.forEach((plane: any) => {
                        const pose = frame.getPose(plane.planeSpace, referenceSpace);
                        if (pose) {
                            let minX = Infinity, maxX = -Infinity;
                            let minZ = Infinity, maxZ = -Infinity;
                            if (plane.polygon && plane.polygon.length > 0) {
                                for (const p of plane.polygon) {
                                    if (p.x < minX) minX = p.x;
                                    if (p.x > maxX) maxX = p.x;
                                    if (p.z < minZ) minZ = p.z;
                                    if (p.z > maxZ) maxZ = p.z;
                                }
                            }
                            const width = minX !== Infinity ? (maxX - minX) : 1.0;
                            const height = minZ !== Infinity ? (maxZ - minZ) : 1.0;

                            const pos = pose.transform.position;
                            const rot = pose.transform.orientation;
                            const normal = new THREE.Vector3(0, 1, 0).applyQuaternion(
                                new THREE.Quaternion(rot.x, rot.y, rot.z, rot.w)
                            );

                            let type: any = 'other';
                            const label = (plane.semanticLabel || '').toLowerCase();
                            if (label.includes('floor')) type = 'floor';
                            else if (label.includes('wall')) type = 'wall';
                            else if (label.includes('ceiling')) type = 'ceiling';
                            else if (label.includes('window')) type = 'window';
                            else if (label.includes('door')) type = 'door';
                            else if (label.includes('table') || label.includes('chair') || label.includes('desk') || label.includes('couch') || label.includes('bed') || label.includes('seat') || label.includes('furniture')) type = 'furniture';
                            else if (label.includes('screen') || label.includes('tv') || label.includes('monitor')) type = 'screen';

                            anchors.push({
                                id: plane.id || `plane_${planeId++}`,
                                type,
                                label: label || undefined,
                                position: { x: pos.x, y: pos.y, z: pos.z },
                                size: { x: width, y: 0.1, z: height },
                                normal: { x: normal.x, y: normal.y, z: normal.z }
                            });
                        }
                    });

                    if (anchors.length > 0) {
                        (window as any).spatialEnvironment.ingestQuestSceneData('Quest Room', anchors);
                        // Rebuild the room scene with the newly detected walls/windows/furniture
                        // and plaster the live webcam onto the wall surfaces
                        const spatialEnvObj = (window as any).spatialEnvironment;
                        if (spatialEnvObj && env) {
                            spatialEnvObj.buildRoomScene(env.scene);
                            // Init live webcam plaster if not already active
                            if (!spatialEnvObj.getWebcamPlasterStatus || !spatialEnvObj.getWebcamPlasterStatus().hasVideo) {
                                const portalVideo = (window as any).foveaiPortalVideo;
                                spatialEnvObj.initLiveWebcamPlaster(portalVideo, 'portrait').then((ok: boolean) => {
                                    if (ok) {
                                        dashboard.log('📹 Live webcam plastered onto room walls (portrait mode)', 'var(--neon-green)');
                                    }
                                }).catch(() => { /* webcam may not be available yet */ });
                            } else {
                                // Webcam already initialized — re-apply to new walls
                                spatialEnvObj.applyLiveWebcamToWalls();
                            }
                        }
                    }
                }
            }
        }

        // --- WEBXR GUIDED SCANNER CAPTURE ---
        if (frame && (window as any).roomScanner && (window as any).roomScanner.isScanning()) {
            if (currentTime - lastScanCaptureTime > 30000) {
                lastScanCaptureTime = currentTime;
                const scanner = (window as any).roomScanner;
                const composite = getCompositeVision();
                if (composite) {
                    composite.captureComposite(env.renderer, env.scene, env.camera, xrCamera)
                        .then((result: any) => {
                            const userForward = new THREE.Vector3(0, 0, -1).applyQuaternion(tempCamQuat);
                            scanner.registerCapture(tempCamPos, userForward, result.base64);
                        })
                        .catch((err: any) => console.warn('[Scanner] Auto-capture frame failed:', err));
                }
            }
        }

        const hudEnabled = localStorage.getItem('foveai_3d_hud_enabled') !== 'false';

        const xr3dHudMesh = (window as any).xr3dHudMesh;
        if (xr3dHudMesh) {
            xr3dHudMesh.visible = hudEnabled;
            if (hudEnabled) {
                const targetPos = new THREE.Vector3(0, -0.15, -1.2).applyQuaternion(tempCamQuat).add(tempCamPos);
                // Snap on first frame, then smoothly lerp to avoid head shake jitter
                if (xr3dHudMesh.position.lengthSq() < 0.001) {
                    xr3dHudMesh.position.copy(targetPos);
                    xr3dHudMesh.quaternion.copy(tempCamQuat);
                } else {
                    xr3dHudMesh.position.lerp(targetPos, 0.03);
                    xr3dHudMesh.quaternion.slerp(tempCamQuat, 0.03);
                }
            }
        }

        const xrPeripheralHudMesh = (window as any).xrPeripheralHudMesh;
        if (xrPeripheralHudMesh) {
            xrPeripheralHudMesh.visible = hudEnabled;
            if (hudEnabled) {
                const targetPos = new THREE.Vector3(0, -0.45, -0.8).applyQuaternion(tempCamQuat).add(tempCamPos);
                if (xrPeripheralHudMesh.position.lengthSq() < 0.001) {
                    xrPeripheralHudMesh.position.copy(targetPos);
                    xrPeripheralHudMesh.quaternion.copy(tempCamQuat);
                } else {
                    xrPeripheralHudMesh.position.lerp(targetPos, 0.03);
                    xrPeripheralHudMesh.quaternion.slerp(tempCamQuat, 0.03);
                }
            }
        }
    }

    const delta = clock.getDelta();

    if (agyAvatar && agyAvatar.vrm) {
        if (env && env.camera) {
            agyAvatar.update(delta, env.camera);
        }
    }

    if (env && env.renderer.xr.enabled && env.renderer.xr.isPresenting) {
        // Throttled update of the HTML Indicator HUD Overlay in VR (runs every 150ms)
        const now = Date.now();
        if (now - lastHudUpdateTime > 150) {
            lastHudUpdateTime = now;
            updateXRIndicatorHub();
            updatePeripheralHUD();
        }
    }

    if (avatar && avatar.vrm) {
        try {
            avatar.update(delta, env.camera);

            // Update user virtual VR avatar representation (tracks headset & controllers)
            updateUserAvatar();

            // Reactively redraw the 3D Holographic Menu Panel in VR when chat or VAD state changes
            // Uses content hash to skip expensive ThreeMeshUI.Text.set() calls when nothing changed
            if (holographicPanelMesh && holographicPanelMesh.visible) {
                const currentHistoryLength = (window as any).foveaiDashboard?.chatHistory?.length || 0;
                const currentListeningState = dashboard?.isListening || false;

                const contentChanged = (currentHistoryLength !== lastChatHistoryLength || currentListeningState !== lastListeningState);

                if (contentChanged) {
                    lastChatHistoryLength = currentHistoryLength;
                    lastListeningState = currentListeningState;

                    // 1. Update Chat History (only if content changed)
                    if (holographicChatText) {
                        const history = (window as any).foveaiDashboard?.chatHistory || [];
                        const lastMessages = history.slice(-5);
                        const formattedText = lastMessages.map((msg: any) => {
                            const roleName = msg.role === 'user' ? 'USER' : (isDevModeActive ? 'CO-DEVELOPER' : 'JEN');
                            const content = msg.content || '';
                            const textVal = content.length > 120 ? content.substring(0, 117) + '...' : content;
                            return `[${roleName}] ${textVal}`;
                        }).join('\n\n');
                        const newContent = formattedText || "FoveAI NATIVE VR DASHBOARD\nConnected to Python Core\nReady for input...";
                        if (_lastHolographicContent['chat'] !== newContent) {
                            _lastHolographicContent['chat'] = newContent;
                            holographicChatText.set({ content: newContent });
                        }
                    }

                    // 2. Update Status Bar (Identity) — only if dev mode state changed
                    if (holographicIdentityText) {
                        const newIdentity = isDevModeActive ? "IDENTITY: CO-DEVELOPER (GEMINI)" : "IDENTITY: JEN COMPANION";
                        if (_lastHolographicContent['identity'] !== newIdentity) {
                            _lastHolographicContent['identity'] = newIdentity;
                            holographicIdentityText.set({
                                content: newIdentity,
                                fontColor: new THREE.Color(isDevModeActive ? 0x00f3ff : 0xff007f)
                            });
                        }
                    }

                    // 3. Update VAD Listening State
                    if (holographicVadText) {
                        const isSpeaking = (window as any).foveaiVideoChat?.isSpeaking || false;
                        let vadContent: string;
                        let vadColor: number;
                        if (isSpeaking) {
                            vadContent = "VAD: JEN SPEAKING";
                            vadColor = 0x39ff14;
                        } else if (currentListeningState) {
                            vadContent = "VAD: LISTENING";
                            vadColor = 0xff007f;
                        } else {
                            vadContent = "VAD: STANDBY";
                            vadColor = 0xaaaaaa;
                        }
                        if (_lastHolographicContent['vad'] !== vadContent) {
                            _lastHolographicContent['vad'] = vadContent;
                            holographicVadText.set({
                                content: vadContent,
                                fontColor: new THREE.Color(vadColor)
                            });
                        }
                    }

                    // 4. Update Thinking & Shadow Warnings
                    if (holographicThinkingText) {
                        let thinkContent: string;
                        let thinkColor: number;
                        if (isBrainThinking) {
                            const queryDuration = Date.now() - lastBrainQueryStartTime;
                            if (queryDuration > 8000) {
                                thinkContent = `⚠️ NEURAL SHADOW (${Math.round(queryDuration / 1000)}s)`;
                                thinkColor = 0xff0000;
                            } else {
                                thinkContent = "THINKING...";
                                thinkColor = 0xff7800;
                            }
                        } else {
                            thinkContent = "READY";
                            thinkColor = 0x39ff14;
                        }
                        if (_lastHolographicContent['thinking'] !== thinkContent) {
                            _lastHolographicContent['thinking'] = thinkContent;
                            holographicThinkingText.set({
                                content: thinkContent,
                                fontColor: new THREE.Color(thinkColor)
                            });
                        }
                    }

                    // 5. Update Dev Feed Status
                    if (holographicDevFeedText) {
                        const cachedFeedEl = document.getElementById('xr-hud-dev-feed-val');
                        const feedText = cachedFeedEl ? cachedFeedEl.textContent || "WAITING..." : "WAITING...";
                        const newFeed = feedText.toUpperCase();
                        if (_lastHolographicContent['devfeed'] !== newFeed) {
                            _lastHolographicContent['devfeed'] = newFeed;
                            holographicDevFeedText.set({
                                content: newFeed,
                                fontColor: feedText.toLowerCase().includes('fail') || feedText.toLowerCase().includes('error')
                                    ? new THREE.Color(0xff0000)
                                    : feedText.toLowerCase().includes('success') || feedText.toLowerCase().includes('done')
                                        ? new THREE.Color(0x39ff14)
                                        : new THREE.Color(0x00f3ff)
                            });
                        }
                    }

                    drawHolographicPanel();
                }
            }

            // 6. Poll XR-IDE edit stream (every 5s)
            if (xrIdeHud) {
                const activeCamera = env.renderer.xr.isPresenting ? env.renderer.xr.getCamera() : env.camera;
                xrIdeHud.update(delta, activeCamera);
                const nowPoll = Date.now();
                if (nowPoll - lastDevEditsPoll > 5000) {
                    lastDevEditsPoll = nowPoll;
                    (async () => {
                        try {
                            const res = await fetch('/api/dev/edits');
                            if (res.ok) { const d = await res.json(); if (d.status === 'ok') xrIdeHud!.setData(d); }
                        } catch (_e) { }
                    })();
                }
            }

            // Touch detection — zone pre-resolved by HapticWand bone-sphere collision (no stutter)
            const handleTouch = (point: THREE.Vector3, pressure: number, isRightHand: boolean, preResolvedZone?: string) => {
                const touchedZone = preResolvedZone || "body";
                const now = Date.now();
                const lastTouchTime = (window as any).foveaiLastTouchTime || 0;
                if (now - lastTouchTime > 3500) {
                    (window as any).foveaiLastTouchTime = now;
                    dashboard.log(`[Haptics] Jen touched on: ${touchedZone} (pressure: ${pressure.toFixed(2)})`, '#ff00aa');
                    // Wand Glow Flare: Make the controller wand mesh material flare glowing gold on hotspot contact
                    const activeWand = isRightHand ? wandRight : wandLeft;
                    if (activeWand) {
                        const mat = (activeWand as any).rodMaterial;
                        if (mat) {
                            const originalColor = isRightHand ? 0xff0088 : 0x00f3ff;
                            const isHotspot = ["chest", "neck", "thigh", "head"].includes(touchedZone);
                            if (isHotspot) {
                                if (mat.color && mat.color.setHex) mat.color.setHex(0xffaa00);
                                if (mat.emissive && mat.emissive.setHex) mat.emissive.setHex(0xffaa00);
                                setTimeout(() => {
                                    if (mat.color && mat.color.setHex) mat.color.setHex(originalColor);
                                    if (mat.emissive && mat.emissive.setHex) mat.emissive.setHex(originalColor);
                                }, 1200);
                            }
                        }
                    }

                    // 1. Resolve physiological sounds, expressions, emotional states & micro-gestures
                    let soundTag = "sigh_content";
                    let expression = "happy";
                    let emoState = "happy";
                    let gesture = "tilt";
                    let remark = "The user reached out and touched you in VR.";

                    if (touchedZone === "head") {
                        soundTag = "sigh_content";
                        expression = "happy";
                        emoState = "calm";
                        gesture = "tilt";
                        remark = "The user gently caressed your cheek/head in VR.";
                    } else if (touchedZone === "neck") {
                        soundTag = "gasp_subtle";
                        expression = "surprised";
                        emoState = "excited";
                        gesture = "tilt";
                        remark = "The user softly stroked your neck in VR, sending a warm shiver through your body.";
                    } else if (touchedZone === "shoulder") {
                        soundTag = "chuckle_warm";
                        expression = "content";
                        emoState = "calm";
                        gesture = "nod";
                        remark = "The user placed a warm, reassuring hand on your shoulder in VR.";
                    } else if (touchedZone === "chest") {
                        soundTag = "gasp_subtle";
                        expression = "surprised";
                        emoState = "excited";
                        gesture = "shake";
                        remark = "The user placed a warm hand on your chest/heart in VR, feeling your heartbeat speed up.";
                    } else if (touchedZone === "hips" || touchedZone === "waist") {
                        soundTag = "laugh_soft";
                        expression = "surprised";
                        emoState = "happy";
                        gesture = "tilt";
                        remark = "The user tickled or held your waist/hips in VR.";
                    } else if (touchedZone === "arm") {
                        soundTag = "hmm_thoughtful";
                        expression = "content";
                        emoState = "calm";
                        gesture = "tilt";
                        remark = "The user gently caressed your arm in VR.";
                    } else if (touchedZone === "hand") {
                        soundTag = "mhm_affirming";
                        expression = "happy";
                        emoState = "happy";
                        gesture = "nod";
                        remark = "The user took hold of your hand or fingers in VR, holding hands.";
                    } else if (touchedZone === "thigh") {
                        soundTag = "gasp_subtle";
                        expression = "surprised";
                        emoState = "excited";
                        gesture = "double_take";
                        remark = "The user gently placed a hand on your thigh/upper leg in VR, which is a highly sensitive hotspot.";
                    } else if (touchedZone === "leg") {
                        soundTag = "laugh_soft";
                        expression = "content";
                        emoState = "happy";
                        gesture = "shake";
                        remark = "The user playfully touched your leg or foot in VR.";
                    }

                    // Play soundboard sound immediately
                    const soundRegistry = (window as any).soundboardRegistry || (window as any).soundboard;
                    if (soundRegistry && typeof soundRegistry.play === 'function') {
                        soundRegistry.play(soundTag);
                    }

                    // Apply emotional states and gestures to the Avatar
                    if (avatar) {
                        avatar.setEmotionalState(emoState);
                        avatar.triggerMicroGesture(gesture);
                    }

                    // 2. Set temporary BlendShape facial reaction
                    if (avatar && avatar.vrm) {
                        avatar.vrm.expressionManager?.setValue(expression as any, 0.8);
                        setTimeout(() => {
                            if (avatar && avatar.vrm) {
                                avatar.vrm.expressionManager?.setValue(expression as any, 0.0);
                            }
                        }, 2000);
                    }

                    // 3. Make head gaze track the touched point (extended to 4s)
                    if (avatar) {
                        avatar.setGazeTarget(point);
                        setTimeout(() => {
                            if (avatar) avatar.clearGazeTarget();
                        }, 4000);
                    }

                    // 4. Send background context for a warm voice whisper response
                    (async () => {
                        try {
                            const soulReply = await fetchSoulFallback(
                                `${remark} Comment on it warmly, affectionately, and intimately in a brief whisper.`,
                                "Touched in VR",
                                false, // deepThought
                                dashboard.privacyMode
                            );
                            if (soulReply) {
                                dashboard.addMessage('assistant', soulReply);
                                videoChat.speak(soulReply);
                            }
                        } catch (err) {
                            console.warn('[Haptics] Failed to get touch voice reaction:', err);
                        }
                    })();
                }
            };

            try {
                if (wandLeft) {
                    wandLeft.update(delta, avatar.vrm, (point, pressure, zone) => handleTouch(point, pressure, false, zone));
                }
                if (wandRight) {
                    wandRight.update(delta, avatar.vrm, (point, pressure, zone) => handleTouch(point, pressure, true, zone));
                }
            } catch (updateErr) {
                console.warn('[Main] Avatar update error:', updateErr);
            }
        } catch (err) {
            console.warn('[Main] Avatar tick/update error:', err);
        }
    }

    const session = (window as any).xrSession;
        if (session && session.inputSources) {
            // Dynamically update VR recording indicator & status based on dashboard listening state
            const recIndicator = document.getElementById('xr-recording-indicator');
            if (recIndicator) {
                recIndicator.style.display = dashboard.isListening ? 'flex' : 'none';
            }
            const statusEl = document.getElementById('xr-controller-status');
            if (statusEl) {
                if (dashboard.isListening) {
                    statusEl.innerHTML = `<span>PAD</span>🎤 SPEAKING [VAD]`;
                    statusEl.style.borderColor = 'var(--neon-pink)';
                } else {
                    const ct = session.inputSources.length;
                    const hands = Array.from(session.inputSources).map((s: any) => s.handedness?.charAt(0).toUpperCase() || '?').join('+');
                    statusEl.innerHTML = `<span>PAD</span>🎮 ${ct} (${hands})`;
                    statusEl.style.borderColor = ct >= 2 ? 'var(--neon-green)' : ct >= 1 ? '#ffaa00' : 'var(--neon-pink)';
                }
            }

            // --- QUEST 3 CONTROLLER MAPPING ---
            // WebXR button indices (per controller):
            //   0: Trigger (index finger)
            //   1: Grip/Squeeze (middle finger)
            //   2: Thumbstick click
            //   3: Menu/Meta button (left controller only on Quest 3)
            //   4: A (right) / X (left)
            //   5: B (right) / Y (left)
            //
            // Axes (per controller, each has its own gamepad):
            //   0: Thumbstick X (-1 left, +1 right)
            //   1: Thumbstick Y (-1 up, +1 down)
            //
            // LEFT CONTROLLER:
            //   Thumbstick: Move (WASD) + Teleport on forward release
            //   Trigger (0): Point / Select
            //   Grip (1) hold: Sprint modifier
            //   Thumbstick click (2): Laser pointer toggle
            //   Double thumbstick click: Attention Call
            //   Menu/Meta (3): In-game menu & chat history (DOM overlay)
            //   X (4): Debug window — diagnosis tab (DOM overlay)
            //   Y (5): Avatar camera snapshot
            //
            // RIGHT CONTROLLER:
            //   Thumbstick: Smooth rotation
            //   Thumbstick click (2): Crouch toggle
            //   Double thumbstick click: Attention Call
            //   Trigger (0): Interact / Confirm
            //   Grip (1) hold: Grab mode
            //   A (4): User camera snapshot + auto-post to chat
            //   B (5) hold: Push to Talk (with XR recording indicator)
            //
            // CHORD INPUTS:
            //   Double Thumbstick click: Attention Call (avatar acknowledges user)
            //   Double Trigger: Toggle haptics wand mode (touch-sensitive magic wands)
            //   Double Grip: Toggle avatar steering mode (3D game character control)

            // Reset controller states before polling each frame
            leftTrigger = false;
            rightTrigger = false;
            leftGrip = false;
            rightGrip = false;

            // --- QUEST 3 CONTROLLER STABILITY ---
            // Quest 3 browser can report fluctuating input source counts (0→1→2→1→0).
            // Cache the last known good state to smooth over transient disconnections.
            if (!(window as any)._xrCtrlCache) {
                (window as any)._xrCtrlCache = { sources: [] as any[], zeroFrames: 0 };
            }
            const _ctrlCache = (window as any)._xrCtrlCache;
            if (session.inputSources.length > 0) {
                _ctrlCache.sources = Array.from(session.inputSources);
                _ctrlCache.zeroFrames = 0;
            } else {
                _ctrlCache.zeroFrames++;
            }
            // Use cached sources for up to 60 frames (~1s) when Quest 3 reports 0 controllers
            const effectiveSources = (session.inputSources.length === 0 && _ctrlCache.sources.length > 0 && _ctrlCache.zeroFrames < 60)
                ? _ctrlCache.sources : Array.from(session.inputSources);

            for (const source of effectiveSources) {
                if (!source.gamepad) continue;
                const gp = source.gamepad;
                let isLeft = source.handedness === 'left';
                let isRight = source.handedness === 'right';
                // Quest 3 fallback: if handedness is not reported, use index-based assignment
                if (!isLeft && !isRight && effectiveSources.length > 0) {
                    const idx = effectiveSources.indexOf(source);
                    if (effectiveSources.length >= 2) {
                        isLeft = idx === 0;
                        isRight = idx === 1;
                    } else if (effectiveSources.length === 1) {
                        isRight = true; // Single controller defaults to right hand
                    }
                }

                // Assign gamepad source references to the active haptic wands for physical variable feedback
                if (isLeft && wandLeft) {
                    wandLeft.gamepad = gp;
                }
                if (isRight && wandRight) {
                    wandRight.gamepad = gp;
                }

                // --- THUMBSTICK INPUT ---
                if (gp.axes.length >= 2) {
                    const sx = gp.axes[0];
                    const sy = gp.axes[1];

                    if (isLeft) {
                        const lx = Math.abs(sx) > thumbstickDeadzone ? sx : 0;
                        const ly = Math.abs(sy) > thumbstickDeadzone ? sy : 0;
                        leftThumbstickX = lx;
                        leftThumbstickY = ly;

                        if (holographicPanelMesh && holographicPanelMesh.visible) {
                            // Left Thumbstick cycles active tab: sx > 0.6 is flick right, sx < -0.6 is flick left
                            const isFlicking = Math.abs(sx) > 0.6;
                            if (isFlicking && !lastLeftThumbstickFlick) {
                                lastLeftThumbstickFlick = true;
                                const dir = sx > 0 ? 1 : -1;
                                const currIdx = holographicTabs.indexOf(activeHolographicTab);
                                let nextIdx = currIdx + dir;
                                if (nextIdx < 0) nextIdx = holographicTabs.length - 1;
                                if (nextIdx >= holographicTabs.length) nextIdx = 0;
                                activeHolographicTab = holographicTabs[nextIdx];

                                // Pulse left controller haptics
                                triggerHaptic(source, 0.4, 60);

                                dashboard.log(`[XR HUD] Switched active tab to: ${activeHolographicTab.toUpperCase()}`, 'var(--neon-blue)');
                                drawHolographicPanel();
                            } else if (!isFlicking) {
                                lastLeftThumbstickFlick = false;
                            }

                            // Force manual velocity to 0 while using HUD menu to avoid walking off
                            if (avatar) {
                                avatar.setManualVelocity(new THREE.Vector3(0, 0, 0));
                            }
                        } else {
                            // --- TELEPORT ON FORWARD RELEASE ---
                            // Push thumbstick forward (Y < -0.5) to aim, release to teleport
                            const isForward = sy < -0.5;
                            if (isForward && !leftThumbstickForward) {
                                leftThumbstickForward = true;
                                // Show teleport marker while aiming
                                if (avatar && avatar.vrm && teleportMarker) {
                                    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(env.camera.quaternion);
                                    fwd.y = 0; fwd.normalize();
                                    const tp = avatar.vrm.scene.position.clone().add(fwd.multiplyScalar(2));
                                    tp.y = 0;
                                    teleportMarker.position.copy(tp);
                                    (teleportMarker.material as THREE.MeshStandardMaterial).opacity = 0.5;
                                }
                            }
                            if (!isForward && leftThumbstickForward) {
                                // Released from forward — teleport!
                                leftThumbstickForward = false;
                                if (avatar && avatar.vrm && !isTeleporting) {
                                    isTeleporting = true;
                                    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(env.camera.quaternion);
                                    fwd.y = 0; fwd.normalize();
                                    const tp = avatar.vrm.scene.position.clone().add(fwd.multiplyScalar(2));
                                    tp.y = 0;
                                    if (teleportMarker) {
                                        teleportMarker.position.copy(tp);
                                        (teleportMarker.material as THREE.MeshStandardMaterial).opacity = 1.0;
                                    }
                                    avatar.vrm.scene.position.x = tp.x;
                                    avatar.vrm.scene.position.z = tp.z;
                                    dashboard.log(`[XR] Teleport to (${tp.x.toFixed(1)}, ${tp.z.toFixed(1)})`, 'var(--neon-blue)');
                                    triggerHaptic(source, 0.8, 80);
                                    setTimeout(() => {
                                        if (teleportMarker) (teleportMarker.material as THREE.MeshStandardMaterial).opacity = 0;
                                        isTeleporting = false;
                                    }, 500);
                                }
                            }
                            // Fade marker if not aiming
                            if (!isForward && !leftThumbstickForward && teleportMarker) {
                                (teleportMarker.material as THREE.MeshStandardMaterial).opacity = 0;
                            }

                            // --- MOVEMENT (lateral always, forward only when not aiming teleport) ---
                            const moveLy = leftThumbstickForward ? 0 : ly;
                            if (avatar && avatar.vrm && (Math.abs(lx) > 0 || Math.abs(moveLy) > 0)) {
                                const sprint = gp.buttons[1]?.pressed ? 2.5 : 1.0;
                                if (avatar.steeringActive) {
                                    // Tank/Steering Controls: Left/right rotates the avatar, up/down moves along her own nose axis
                                    // lx rotates the avatar body (yaw)
                                    avatar.vrm.scene.rotation.y -= lx * 3.0 * delta; // 3.0 rad/s max rotation
                                    // moveLy moves forward/backward relative to avatar's own orientation
                                    const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(avatar.vrm.scene.quaternion);
                                    avatar.setManualVelocity(forward.multiplyScalar(-moveLy * movementSpeed * sprint));
                                } else {
                                    // Default Controls: move relative to camera
                                    const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(env.camera.quaternion);
                                    forward.y = 0;
                                    forward.normalize();
                                    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(env.camera.quaternion);
                                    right.y = 0;
                                    right.normalize();

                                    const moveDir = forward.multiplyScalar(-moveLy * movementSpeed * sprint)
                                        .add(right.multiplyScalar(lx * movementSpeed * sprint));

                                    avatar.setManualVelocity(moveDir);
                                }
                            } else if (avatar) {
                                avatar.setManualVelocity(new THREE.Vector3(0, 0, 0));
                            }
                        }
                    }

                    if (isRight) {
                        // Right thumbstick: Smooth rotation (when menu closed) or scroll (when menu open)
                        const isMenuOpen = !!(holographicPanelMesh && holographicPanelMesh.visible);
                        const rx = Math.abs(sx) > thumbstickDeadzone ? sx : 0;
                        const ry = Math.abs(sy) > thumbstickDeadzone ? sy : 0;

                        if (isMenuOpen) {
                            // SCROLL the active tab content using right thumbstick Y axis
                            if (Math.abs(ry) > 0.15 || Math.abs(rx) > 0.15) {
                                const dashboardDom = document.getElementById('foveai-dashboard');
                                if (dashboardDom) {
                                    const activeTab = (dashboard as any)?.activeTab || 'cognition';
                                    const TAB_SCROLL_IDS: Record<string, string> = {
                                        'cognition': '#chat-history',
                                        'thoughts': '#thought-history-list',
                                        'settings': '#settings-tab',
                                        'profile': '#profile-tab-content',
                                        'swarm': '#swarm-tab-content',
                                        'agency': '#agency-tab-content',
                                        'chronicle': '#chronicle-tab-content',
                                        'modelhub': '#modelhub-tab-content',
                                        'dreamscape': '#dreamscape-tab-content',
                                        'devtools': '#devtools-tab-content',
                                        'nucleus': '#nucleus-tab-content',
                                        'diagnosis': '#diagnosis-tab-content',
                                        'vision': '#vision-tab-content',
                                        'branding': '#branding-tab-content',
                                        'monetizing': '#monetizing-tab-content',
                                        'webvm': '#webvm-tab-content',
                                        'featuremap': '#featuremap-tab-content',
                                        'forgeindex': '#forgeindex-tab-content',
                                    };
                                    const scrollId = TAB_SCROLL_IDS[activeTab];
                                    let scrollEl: HTMLElement | null = scrollId
                                        ? dashboardDom.querySelector(scrollId) as HTMLElement | null
                                        : null;
                                    if (!scrollEl) {
                                        scrollEl = dashboardDom.querySelector('#tab-content-area') as HTMLElement | null;
                                    }
                                    if (!scrollEl) {
                                        scrollEl = dashboardDom.querySelector('.tab-content') as HTMLElement | null;
                                    }

                                    let didScroll = false;
                                    if (scrollEl && Math.abs(ry) > 0.15) {
                                        scrollEl.scrollTop += ry * 1200 * delta;
                                        didScroll = true;
                                    }
                                    if (scrollEl && Math.abs(rx) > 0.15) {
                                        scrollEl.scrollLeft += rx * 1200 * delta;
                                        didScroll = true;
                                    }

                                    if (didScroll && holographicPanelMesh) {
                                        try {
                                            (holographicPanelMesh.material as any).map.needsUpdate = true;
                                            window.dispatchEvent(new Event('resize'));
                                        } catch (e) { }
                                    }
                                }
                            }
                        } else if (Math.abs(rx) > 0) {
                            env.camera.rotation.y -= rx * rotationSpeed * delta;
                        }
                    }
                }

                // --- TRIGGERS (Button 0) ---
                const triggerPressed = gp.buttons[0]?.pressed || false;
                if (isLeft) leftTrigger = triggerPressed;
                if (isRight) rightTrigger = triggerPressed;
                if (isRight && triggerPressed && !lastTriggerState[1]) {
                    dashboard.log('[XR] Right Trigger: Interact', 'var(--neon-blue)');
                    triggerHaptic(source, 0.5, 50);
                }
                if (isLeft && triggerPressed && !lastTriggerState[0]) {
                    dashboard.log('[XR] Left Trigger: Point', 'var(--neon-blue)');
                }

                // --- GRIP BUTTONS (Button 1) ---
                const gripPressed = gp.buttons[1]?.pressed || false;
                if (isLeft) leftGrip = gripPressed;
                if (isRight) rightGrip = gripPressed;

                // --- MENU/META BUTTON (Button 3) ---
                // Left menu/meta opens/closes the holographic panel. Right meta toggles XR-IDE HUD.
                // Both require a 500ms cooldown after last toggle.
                if (gp.buttons.length > 3) {
                    const menuPressed = gp.buttons[3]?.pressed || false;
                    if (isLeft) {
                        if (menuPressed && !lastMenuButtonState) {
                            const now = Date.now();
                            if (now - lastXrIdeHudToggle > 500) {
                                lastXrIdeHudToggle = now;
                                dashboard.log('[XR] Left Menu/Meta pressed', 'var(--neon-blue)');
                                const panelCurrentlyVisible = !!(holographicPanelMesh?.visible);
                                const targetState = !panelCurrentlyVisible;
                                toggleHolographicPanel(targetState);
                                dashboard.toggle(targetState);
                                if (targetState) {
                                    dashboard.setActiveTab('cognition');
                                    dashboard.log('[XR] Menu/Meta: holographic panel opened', 'var(--neon-pink)');
                                } else {
                                    dashboard.log('[XR] Menu/Meta: holographic panel closed', 'var(--neon-pink)');
                                }
                                triggerHaptic(source, 0.3, 30);
                            }
                        }
                        lastMenuButtonState = !!menuPressed;
                        lastLeftMetaButtonState = !!menuPressed;
                    }
                    if (isRight) {
                        if (menuPressed && !lastRightMetaButtonState) {
                            const now = Date.now();
                            if (now - lastXrIdeHudToggle > 500) {
                                lastXrIdeHudToggle = now;
                                dashboard.log('[XR] Right Meta pressed', 'var(--neon-blue)');
                                // Right Meta now also toggles the beautiful HTML dashboard instead of the legacy XR-IDE HUD
                                const panelCurrentlyVisible = !!(holographicPanelMesh?.visible);
                                toggleHolographicPanel(!panelCurrentlyVisible);
                                dashboard.log(`[XR] Right Meta: Menu ${!panelCurrentlyVisible ? 'opened' : 'closed'}`, 'var(--neon-green)');
                                triggerHaptic(source, 0.3, 30);
                            }
                        }
                        lastRightMetaButtonState = !!menuPressed;
                    }
                }

                // --- THUMBSTICK CLICK (Button 2) ---
                // Single click: Laser (left) / Crouch (right)
                // Double click: Attention Call (either controller)
                const thumbstickClick = gp.buttons[2]?.pressed || false;
                const clickIdx = isRight ? 1 : 0;
                if (thumbstickClick && !lastThumbstickClickState[clickIdx]) {
                    // Immediate subtle haptic on any click
                    triggerHaptic(source, 0.2, 15);

                    if (thumbstickClickPending[clickIdx]) {
                        // Double click! Cancel pending single-click and fire Attention Call
                        clearTimeout(thumbstickClickTimer[clickIdx]);
                        thumbstickClickPending[clickIdx] = false;

                        dashboard.log('[XR] Double Thumbstick: Attention Call', 'var(--neon-pink)');
                        triggerHaptic(source, 0.6, 60);
                        if (avatar) {
                            avatar.playCategory('Happy', false, 0.5); // Fixed: loop=false so she returns to idle
                        }
                        (async () => {
                            try {
                                const soulReply = await fetchSoulFallback(
                                    "The user just called for your attention. Give a brief, warm acknowledgment. Keep it to one short sentence.",
                                    "Attention Call"
                                );
                                const greetingText = soulReply || "I'm here. What can I do for you?";
                                dashboard.addMessage('assistant', greetingText);
                                videoChat.speak(greetingText);
                            } catch (err) {
                                dashboard.log(`Attention call error: ${err}`, '#ff007f');
                            }
                        })();
                    } else {
                        // First click — set pending timer for single-click action
                        thumbstickClickPending[clickIdx] = true;
                        const capturedIsRight = isRight;
                        thumbstickClickTimer[clickIdx] = window.setTimeout(() => {
                            thumbstickClickPending[clickIdx] = false;
                            // Fire single-click action
                            if (capturedIsRight) {
                                // Right: Crouch toggle
                                isCrouching = !isCrouching;
                                dashboard.log(`[XR] Right Thumbstick: Crouch ${isCrouching ? 'ON' : 'OFF'}`, 'var(--neon-blue)');
                                if (avatar) {
                                    avatar.isCrouching = isCrouching;
                                }
                            } else {
                                // Left: Toggle laser pointer
                                laserPointerActive = !laserPointerActive;
                                dashboard.log(`[XR] Left Thumbstick: Laser ${laserPointerActive ? 'ON' : 'OFF'}`, 'var(--neon-blue)');
                                if (laserBeam) {
                                    (laserBeam.material as THREE.LineBasicMaterial).opacity = laserPointerActive ? 0.8 : 0.0;
                                }
                            }
                        }, THUMBSTICK_DOUBLE_THRESHOLD);
                    }
                }
                lastThumbstickClickState[clickIdx] = thumbstickClick;

                // --- A/X BUTTON (Button 4) ---
                const abPressed = gp.buttons[4]?.pressed || false;
                if (abPressed && !lastABState[isRight ? 1 : 0]) {
                    if (isRight) {
                        // Anti-spam debounce (2000ms cooldown)
                        const now = Date.now();
                        if (!(window as any).lastSnapshotTime) (window as any).lastSnapshotTime = 0;
                        if (now - (window as any).lastSnapshotTime < 2000) {
                            lastABState[isRight ? 1 : 0] = abPressed;
                            continue; // Skip processing to prevent queue flooding
                        }
                        (window as any).lastSnapshotTime = now;

                        // A button: User camera snapshot — capture and auto-post to chat for avatar delivery
                        triggerUserSnapshot();
                        triggerHaptic(source, 0.5, 60);
                    }
                    if (isLeft) {
                        // X button: Toggle holographic panel (show/hide the 3D UI panel)
                        const now = Date.now();
                        if (now - lastXrIdeHudToggle > 500) {
                            lastXrIdeHudToggle = now;
                            const panelCurrentlyVisible = !!(holographicPanelMesh?.visible);
                            const targetState = !panelCurrentlyVisible;
                            toggleHolographicPanel(targetState);
                            // xrIdeHud is now explicitly disabled to prevent overlap
                            dashboard.toggle(targetState);

                            if (targetState) {
                                dashboard.setActiveTab('cognition');
                                dashboard.log('[XR] X: Holographic panel opened', 'var(--neon-green)');
                            } else {
                                dashboard.log('[XR] X: Holographic panel closed', 'var(--neon-pink)');
                            }
                            triggerHaptic(source, 0.3, 30);
                        }
                    }
                }
                lastABState[isRight ? 1 : 0] = abPressed;

                // --- B/Y BUTTON (Button 5) ---
                if (gp.buttons.length > 5) {
                    const byPressed = gp.buttons[5]?.pressed || false;

                    if (isRight) {
                        // B button: Toggle Voice Activity Detection (VAD) Speech-to-Text
                        if (byPressed && !rightBHeld) {
                            rightBHeld = true;

                            // Validate mic access
                            const cachedMic = (window as any).foveaiCachedMicStream as MediaStream | null;
                            if (!cachedMic && !navigator.mediaDevices) {
                                dashboard.log('[XR] B: STT FAILED — no microphone access', '#ff007f');
                            } else {
                                if (dashboard.isListening) {
                                    dashboard.log('[XR] B: VAD STT stopped manually', 'var(--neon-pink)');
                                    userWantsVad = false;
                                    dashboard.stopListening();
                                    triggerHaptic(source, 0.3, 30);
                                } else {
                                    dashboard.log('[XR] B: VAD STT activated (listening...)', 'var(--neon-green)');
                                    userWantsVad = true;
                                    dashboard.startListening();
                                    triggerHaptic(source, 0.5, 50);
                                }
                            }
                        }
                        if (!byPressed && rightBHeld) {
                            rightBHeld = false;
                        }
                    }

                    if (isLeft) {
                        // Y button
                        if (byPressed && !lastBYState[0]) {
                            if (isDevModeActive && xrIdeHud?.isVisible()) {
                                dashboard.log('[XR-IDE] Rollback requested via Y button', '#ffaa00');
                                (async () => {
                                    try {
                                        const res = await fetch('/api/dev/rollback', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ path: '' })
                                        });
                                        const data = await res.json();
                                        if (data.status === 'ok') {
                                            dashboard.log('[XR-IDE] Rollback complete', '#39ff14');
                                        } else {
                                            dashboard.log(`[XR-IDE] Rollback failed: ${data.message || 'unknown'}`, '#ff007f');
                                        }
                                    } catch (e) {
                                        dashboard.log(`[XR-IDE] Rollback error: ${e}`, '#ff007f');
                                    }
                                })();
                                triggerHaptic(source, 0.6, 60);
                            } else {
                                // Avatar camera snapshot (from avatar's head, looking where nose points)
                                triggerAvatarSnapshot();
                                triggerHaptic(source, 0.5, 60);
                            }
                        }
                    }

                    lastBYState[isRight ? 1 : 0] = byPressed;
                }
            }

            // --- HUD INTERACTION (RAYCASTING & CLICKS) ---
            (window as any).ThreeMeshUI?.update();

            let cursorActive = false;
            let xrIdeHitThisFrame: THREE.Intersection | null = null;
            let xrIdeHitByHand: string | null = null;
            let xrIdeTriggerClickedThisFrame = false;
            if (holographicPanelMesh && holographicPanelMesh.visible) {
                const raycaster = new THREE.Raycaster();
                const tempMatrix = new THREE.Matrix4();

                const leftCtrl = env.renderer.xr.getController(0);
                const rightCtrl = env.renderer.xr.getController(1);

                // Reset all to idle first once per frame to prevent multi-controller reset conflicts
                const uiMeshes = (window as any).foveaiUiMeshes || [];
                uiMeshes.forEach((mesh: any) => {
                    if (mesh.isUI) mesh.setState('idle');
                });

                let anyHovered = false;

                for (const src of effectiveSources) {
                    if (src.targetRaySpace) {
                        const isRightHand = src.handedness === 'right';
                        const controllerGroup = isRightHand ? rightCtrl : leftCtrl;

                        if (controllerGroup) {
                            const gp = src.gamepad;
                            if (isDraggingMenu && draggingHand === (isRightHand ? 'right' : 'left') && gp) {
                                const gripPressed = gp.buttons[1]?.pressed || false;
                                if (!gripPressed) {
                                    // Release drag!
                                    if (holographicPanelMesh) {
                                        if (originalParent) {
                                            originalParent.attach(holographicPanelMesh);
                                        } else {
                                            env.scene.attach(holographicPanelMesh);
                                        }
                                    }
                                    isDraggingMenu = false;
                                    draggingHand = null;
                                    originalParent = null;
                                    dashboard.log('[XR] Released settings panel', 'var(--neon-blue)');
                                    triggerHaptic(src, 0.4, 30);
                                } else {
                                    // Dragging active: resize/tilt check using joystick axes
                                    const joystickY = gp.axes.length > 3 ? gp.axes[3] : (gp.axes[1] || 0); // vertical (scale)
                                    const joystickX = gp.axes.length > 2 ? gp.axes[2] : (gp.axes[0] || 0); // horizontal (tilt)

                                    const scaleDeadzone = 0.2;
                                    const tiltDeadzone = 0.55; // Large deadzone to prevent accidental triggers (deadspace)

                                    if (holographicPanelMesh) {
                                        // 1. Vertical thumbstick: Scale the panel size
                                        if (Math.abs(joystickY) > scaleDeadzone) {
                                            let currentScale = holographicPanelMesh.scale.x;
                                            const scaleDelta = -joystickY * 1.5 * delta; // Scale speed factor
                                            currentScale = Math.max(0.5, Math.min(5.0, currentScale + scaleDelta));
                                            holographicPanelMesh.scale.setScalar(currentScale);
                                            triggerHaptic(src, 0.15, 10);
                                        }

                                        // 2. Horizontal thumbstick: Tilt the panel (yaw rotation around local Y-axis)
                                        // Pushed past large deadzone, and dominant over vertical axis to prevent accidental drift while scaling
                                        if (Math.abs(joystickX) > tiltDeadzone && Math.abs(joystickX) > Math.abs(joystickY) * 1.5) {
                                            const rotationSpeed = 2.0; // Radians per second speed factor
                                            holographicPanelMesh.rotation.y += joystickX * rotationSpeed * delta;
                                            triggerHaptic(src, 0.15, 10);
                                        }
                                    }
                                    // Skip raycasting since we are already dragging/grabbing it!
                                    continue;
                                }
                            }
                            tempMatrix.identity().extractRotation(controllerGroup.matrixWorld);
                            const dir = new THREE.Vector3(0, 0, -1).applyMatrix4(tempMatrix);
                            const pos = new THREE.Vector3().setFromMatrixPosition(controllerGroup.matrixWorld);

                            raycaster.set(pos, dir);

                            // Check intersection with three-mesh-ui components
                            let intersects: THREE.Intersection[] = [];
                            try {
                                const safeUiMeshes = uiMeshes.filter((m: any) => m != null && m !== undefined);
                                intersects = raycaster.intersectObjects(safeUiMeshes, true);
                            } catch (err) {
                                console.warn('[XR] Raycast uiMeshes error:', err);
                            }

                            // Filter out hits on transparent pixels of HTMLMesh objects (HUD and peripheral)
                            const hud3d = (window as any).xr3dHudMesh;
                            const peripheral = (window as any).xrPeripheralHudMesh;
                            intersects = intersects.filter(hit => {
                                let targetObj = hit.object;
                                while (targetObj && targetObj !== env.scene) {
                                    if (targetObj === hud3d || targetObj === peripheral) {
                                        return !isHTMLMeshPixelTransparent(hit);
                                    }
                                    targetObj = targetObj.parent as any;
                                }
                                return true;
                             });

                            // Check intersection with XR-IDE Dev HUD
                            let xrIdeIntersect: THREE.Intersection | null = null;
                            if (xrIdeHud?.isVisible()) {
                                const ideTargets = xrIdeHud.getInteractables();
                                const ideHits = raycaster.intersectObjects(ideTargets, true);
                                if (ideHits.length && (!intersects.length || ideHits[0].distance < intersects[0].distance)) {
                                    xrIdeIntersect = ideHits[0];
                                }
                            }

                            if (intersects.length > 0 || xrIdeIntersect) {
                                const intersect = xrIdeIntersect || intersects[0];
                                const hoveredBlock = intersect.object.parent as any;

                                anyHovered = true;

                                // Scale laser to end exactly at the intersection point
                                if (isRightHand && laserBeamRight) {
                                    laserBeamRight.scale.z = intersect.distance / 5.0;
                                } else if (!isRightHand && laserBeam) {
                                    laserBeam.scale.z = intersect.distance / 5.0;
                                }

                                let isPanelHit = false;
                                let isHudHit = false;
                                let isPeripheralHit = false;
                                let currObj: THREE.Object3D | null = intersect.object;
                                while (currObj) {
                                    if (currObj === holographicPanelMesh) {
                                        isPanelHit = true;
                                        break;
                                    }
                                    if (currObj === hud3d) {
                                        isHudHit = true;
                                        break;
                                    }
                                    if (currObj === peripheral) {
                                        isPeripheralHit = true;
                                        break;
                                    }
                                    currObj = currObj.parent;
                                }

                                // Position the cursor ring exactly at the intersection point, 
                                // but pull it slightly towards the camera to avoid Z-fighting with HTMLMesh sub-elements
                                const cursorDot = isRightHand ? holographicCursorRight : holographicCursorMesh;
                                if (cursorDot) {
                                    cursorDot.position.copy(intersect.point);
                                    cursorDot.position.addScaledVector(raycaster.ray.direction, -0.005);
                                    cursorDot.visible = true;
                                    cursorActive = true;
                                }

                                // Apply hover state or click state for HTMLMesh
                                if ((isPanelHit || isHudHit || isPeripheralHit) && intersect.uv) {
                                    const uv = intersect.uv;
                                    const gp = src.gamepad;

                                    let targetMesh: any = holographicPanelMesh;
                                    if (isHudHit) targetMesh = hud3d;
                                    if (isPeripheralHit) targetMesh = peripheral;

                                    if (targetMesh) {
                                        // Send mousemove with flipped Y (HTML coordinates start at top-left)
                                        (targetMesh as any).dispatchEvent({
                                            type: 'mousemove',
                                            data: new THREE.Vector2(uv.x, 1 - uv.y)
                                        });

                                        if (gp) {
                                            const gripPressed = gp.buttons[1]?.pressed || false;
                                            if (gripPressed && !isDraggingMenu && targetMesh === holographicPanelMesh) {
                                                isDraggingMenu = true;
                                                draggingHand = isRightHand ? 'right' : 'left';
                                                originalParent = holographicPanelMesh?.parent || env.scene;
                                                if (controllerGroup && holographicPanelMesh) {
                                                    controllerGroup.attach(holographicPanelMesh);
                                                    dashboard.log('[XR] Grabbed settings panel to drag', 'var(--neon-green)');
                                                    triggerHaptic(src, 0.6, 60);
                                                }
                                                continue;
                                            }

                                            const triggerPressed = gp.buttons[0]?.pressed || false;
                                            const wasPressed = lastTriggerState[isRightHand ? 1 : 0];

                                            if (triggerPressed && !wasPressed) {
                                                triggerHaptic(src, 0.5, 40);
                                                (targetMesh as any).dispatchEvent({
                                                    type: 'mousedown',
                                                    data: new THREE.Vector2(uv.x, 1 - uv.y)
                                                });
                                            } else if (!triggerPressed && wasPressed) {
                                                (targetMesh as any).dispatchEvent({
                                                    type: 'mouseup',
                                                    data: new THREE.Vector2(uv.x, 1 - uv.y)
                                                });
                                            }
                                        }
                                    }
                                }

                                // Apply hover state or click state
                                if (hoveredBlock && hoveredBlock.isUI) {
                                    // Handle trigger click
                                    const gp = src.gamepad;
                                    let triggerClicked = false;
                                    if (gp) {
                                        const triggerPressed = gp.buttons[0]?.pressed || false;
                                        triggerClicked = triggerPressed && !lastTriggerState[isRightHand ? 1 : 0];
                                        if (triggerClicked) {
                                            triggerHaptic(src, 0.5, 40);
                                        }
                                    }

                                    if (triggerClicked) {
                                        hoveredBlock.setState('selected');
                                    } else {
                                        hoveredBlock.setState('hovered');
                                    }
                                } else if (xrIdeIntersect) {
                                    // XR-IDE hover feedback
                                    const gp = src.gamepad;
                                    let triggerClicked = false;
                                    if (gp) {
                                        const triggerPressed = gp.buttons[0]?.pressed || false;
                                        triggerClicked = triggerPressed && !lastTriggerState[isRightHand ? 1 : 0];
                                        if (triggerClicked) {
                                            triggerHaptic(src, 0.5, 40);
                                        }
                                    }
                                    // Record the closest hit and click state across hands, then dispatch once
                                    if (!xrIdeHitThisFrame || xrIdeIntersect.distance < xrIdeHitThisFrame.distance) {
                                        xrIdeHitThisFrame = xrIdeIntersect;
                                        xrIdeHitByHand = src.handedness || 'right';
                                        xrIdeTriggerClickedThisFrame = triggerClicked;
                                    }
                                }
                            } else if (xrIdeHud?.isVisible()) {
                                xrIdeHud.onPointerMove(null);
                            }
                        }
                    }
                }
            }

            if (xrIdeHitThisFrame && xrIdeHud) {
                xrIdeHud.onPointerMove(xrIdeHitThisFrame);
                if (xrIdeTriggerClickedThisFrame) {
                    xrIdeHud.onPointerSelect(xrIdeHitThisFrame);
                }
            }

            if (!cursorActive) {
                if (holographicCursorMesh) holographicCursorMesh.visible = false;
                if (holographicCursorRight) holographicCursorRight.visible = false;
            }

            // --- LASER POINTER UPDATE ---
            // Show lasers only if a menu is open (main holographic panel OR XR-IDE HUD)
            const hudOpen = !!(holographicPanelMesh && holographicPanelMesh.visible);
            const ideOpen = !!(xrIdeHud && xrIdeHud.isVisible());
            const showLeftLaser = hudOpen || ideOpen;
            const showRightLaser = hudOpen || ideOpen;

            // Ensure layer 1 (mask/ui) is disabled on cameras to prevent UI bleeding
            env.camera.layers.disable(1);
            env.camera.children.forEach(child => child.layers.disable(1));

            const leftCtrl = env.renderer.xr.getController(0);
            const rightCtrl = env.renderer.xr.getController(1);

            if (laserBeam) {
                let laserPlaced = false;
                if (showLeftLaser) {
                    for (const src of effectiveSources) {
                        if (src.handedness === 'left' && src.targetRaySpace) {
                            const ctrl = leftCtrl;
                            if (ctrl) {
                                const pos = new THREE.Vector3();
                                const quat = new THREE.Quaternion();
                                ctrl.getWorldPosition(pos);
                                ctrl.getWorldQuaternion(quat);
                                laserBeam.position.copy(pos);
                                laserBeam.quaternion.copy(quat);
                                // Reset scale to full length each frame — raycaster shortens it on hit
                                laserBeam.scale.z = 1.0;
                                laserPlaced = true;
                                break;
                            }
                        }
                    }
                }
                (laserBeam.material as THREE.LineBasicMaterial).opacity = laserPlaced ? 0.55 : 0.0;
                laserBeam.visible = laserPlaced;
            }

            if (laserBeamRight) {
                let laserPlaced = false;
                if (showRightLaser) {
                    for (const src of effectiveSources) {
                        if (src.handedness === 'right' && src.targetRaySpace) {
                            const ctrl = rightCtrl;
                            if (ctrl) {
                                const pos = new THREE.Vector3();
                                const quat = new THREE.Quaternion();
                                ctrl.getWorldPosition(pos);
                                ctrl.getWorldQuaternion(quat);
                                laserBeamRight.position.copy(pos);
                                laserBeamRight.quaternion.copy(quat);
                                // Reset scale to full length each frame — raycaster shortens it on hit
                                laserBeamRight.scale.z = 1.0;
                                laserPlaced = true;
                                break;
                            }
                        }
                    }
                }
                (laserBeamRight.material as THREE.LineBasicMaterial).opacity = laserPlaced ? 0.55 : 0.0;
                laserBeamRight.visible = laserPlaced;
            }

            // --- TRIGGER CHORD: Both triggers held = toggle haptics wand mode ---
            // Enables 3dm touch-sensitive magic wands that vibrate on contact
            const isTriggerChordActive = leftTrigger && rightTrigger;
            const isDoubleTriggerEnabled = (window as any).doubleTriggerHaptics !== false;

            if (isDoubleTriggerEnabled) {
                if (isTriggerChordActive && !lastTriggerChordState) {
                    hapticsWandMode = !hapticsWandMode;
                    dashboard.log(`[XR] Haptics Wand: ${hapticsWandMode ? 'ENGAGED' : 'DISENGAGED'}`, 'var(--neon-pink)');
                    window.dispatchEvent(new CustomEvent('foveai_toggle_haptics_wand', { detail: hapticsWandMode }));

                    if (wandLeft) wandLeft.setActive(hapticsWandMode);
                    if (wandRight) wandRight.setActive(hapticsWandMode);

                    // Haptic burst on both controllers to confirm state transition
                    for (const src of effectiveSources) {
                        triggerHaptic(src.gamepad, hapticsWandMode ? 0.8 : 0.2, hapticsWandMode ? 100 : 30);
                    }
                }
            } else {
                if (hapticsWandMode) {
                    hapticsWandMode = false;
                    window.dispatchEvent(new CustomEvent('foveai_toggle_haptics_wand', { detail: false }));
                    if (wandLeft) wandLeft.setActive(false);
                    if (wandRight) wandRight.setActive(false);
                    dashboard.log(`[XR] Haptics Wand: DISENGAGED (UI disabled)`, 'var(--neon-pink)');
                }
            }
            lastTriggerChordState = isTriggerChordActive;

            // --- GRIP CHORD: Both grips held = toggle avatar steering mode ---
            // Remaps controllers to 3D game character control
            const isGripChordActive = leftGrip && rightGrip;
            const isDoubleGripEnabled = (window as any).doubleGripSteering !== false;

            if (isDoubleGripEnabled) {
                if (isGripChordActive && !lastGripChordState) {
                    if (avatar) {
                        avatar.steeringActive = !avatar.steeringActive;
                        dashboard.log(`[XR] Steering: ${avatar.steeringActive ? 'ENGAGED' : 'DISENGAGED'}`, 'var(--neon-pink)');

                        // Short haptic pulse to confirm state transition
                        for (const src of effectiveSources) {
                            triggerHaptic(src.gamepad, avatar.steeringActive ? 0.8 : 0.2, avatar.steeringActive ? 100 : 30);
                        }

                        if (!avatar.steeringActive) {
                            avatar.setManualVelocity(new THREE.Vector3(0, 0, 0));
                        }
                    }
                }
            } else {
                if (avatar && avatar.steeringActive) {
                    avatar.steeringActive = false;
                    avatar.setManualVelocity(new THREE.Vector3(0, 0, 0));
                    dashboard.log(`[XR] Steering: DISENGAGED (UI disabled)`, 'var(--neon-pink)');
                }
            }
            lastGripChordState = isGripChordActive;

            // Update previous frame states at the very end of the frame
            lastTriggerState[0] = leftTrigger;
            lastTriggerState[1] = rightTrigger;
        }

        // ── "Be Jen" POV: render from Jen's head camera instead of user camera ──
        if (jenPovActive && jenPovCamera && avatar && avatar.vrm) {
            updateJenPovCamera();
            // Temporarily disable XR so we render to the canvas directly (not the headset)
            const wasXREnabled = env.renderer.xr.enabled;
            if (wasXREnabled) env.renderer.xr.enabled = false;
            env.renderer.render(env.scene, jenPovCamera);
            if (wasXREnabled) env.renderer.xr.enabled = true;
        } else {
            env.renderer.render(env.scene, env.camera);
        }
    }

    // Only start render loop if environment exists
    // Use setAnimationLoop for proper WebXR support
    if (shouldInit3D && env) {
        env.renderer.setAnimationLoop(render);
    }

    boot();

    // ═══════════════════════════════════════════════════════════════
    // ── Director Voice: connect to WebSocket for director.* events ──
    // The Director daemon sends narration, suspense, and event payloads
    // through the XRLF WebSocket (port 8403). We listen for these and
    // route narrator lines through the spooky pitch-down voice engine.
    // ═══════════════════════════════════════════════════════════════
    directorVoice.setLogFn((msg: string, color?: string) => dashboard.log(msg, color || '#8a7a5a'));

    function connectDirectorWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.hostname || '127.0.0.1';
        const wsPort = '8403';
        const wsUrl = `${wsProtocol}//${wsHost}:${wsPort}`;

        try {
            const ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                dashboard.log('[Director] WebSocket connected — spooky narrator ready', '#8a7a5a');
            };

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    const eventType = msg.event || msg.type || '';

                    // Route director events to the voice engine
                    if (eventType === 'director.narration') {
                        const lines = msg.payload?.narratorLines || msg.payload?.lines || [];
                        const text = Array.isArray(lines) ? lines.join(' ') : (typeof lines === 'string' ? lines : '');
                        if (text) directorVoice.speakNarrator(text);
                    } else if (eventType === 'director.event') {
                        const narratorIntro = msg.payload?.narratorIntro || '';
                        if (narratorIntro) directorVoice.speakNarrator(narratorIntro);

                        // Start Avalanche music for suspense/horror genres
                        const genre = msg.payload?.genre || '';
                        if (['Horror', 'NoirMystery', 'SurrealDream', 'WarDrama'].includes(genre)) {
                            if (!directorVoice.isMusicPlaying) {
                                directorVoice.startAvalancheMusic();
                            }
                        }
                    } else if (eventType === 'director.suspense.build') {
                        // Start the dark ambient music during suspense buildup
                        if (!directorVoice.isMusicPlaying) {
                            directorVoice.startAvalancheMusic();
                        }
                        const intensity = msg.payload?.intensity || 0.5;
                        directorVoice.setMusicVolume(0.1 + intensity * 0.15);
                    } else if (eventType === 'director.suspense.abort') {
                        // Fade out the music if suspense is aborted
                        directorVoice.stopAvalancheMusic();
                    } else if (eventType === 'director.tts') {
                        // Director-triggered TTS for characters
                        const text = msg.payload?.text || '';
                        const voice = msg.payload?.voice || 'low';
                        if (text) {
                            if (voice === 'low' || voice === 'gravel') {
                                directorVoice.speakNarrator(text);
                            } else {
                                // Other character voices use normal speech
                                videoChat.speak(text);
                            }
                        }
                    }
                } catch (e) {
                    // Not JSON or parse error — ignore
                }
            };

            ws.onclose = () => {
                dashboard.log('[Director] WebSocket disconnected — will retry in 10s', '#8a7a5a');
                setTimeout(connectDirectorWebSocket, 10000);
            };

            ws.onerror = () => {
                // Silent — onclose will handle reconnection
            };
        } catch (e) {
            console.warn('[Director] WebSocket connection failed:', e);
            setTimeout(connectDirectorWebSocket, 10000);
        }
    }
    // Delay initial connection to allow the runtime to start
    setTimeout(connectDirectorWebSocket, 5000);

    // --- BRAIN DIAGNOSTIC (call from browser console: foveaiBrainDiagnostic()) ---
    (window as any).foveaiBrainDiagnostic = async () => {
        const bs = (window as any).foveaiBrainState;
        console.log('=== FoveAI BRAIN DIAGNOSTIC ===');
        console.log('Brain state:', JSON.stringify(bs, null, 2));

        // Test backend diagnostic endpoint
        try {
            const resp = await fetch('/api/brain/diagnostic');
            if (resp.ok) {
                const data = await resp.json();
                console.log('Backend diagnostic:', JSON.stringify(data, null, 2));
                (window as any).log?.(`Brain diagnostic: Soul=${data.soul?.reachable}, Cloud slots=${data.direct_cloud?.slots_eligible?.length || 0}`, 'var(--neon-blue)');
                if (data.direct_cloud?.test_result) {
                    const tr = data.direct_cloud.test_result;
                    (window as any).log?.(`Cloud test (${tr.slot}): ${tr.success ? 'OK' : 'FAIL'} — ${(tr.reply_preview || tr.error || '').substring(0, 80)}`, tr.success ? '#39ff14' : '#ff007f');
                }
                if (data.routing) {
                    (window as any).log?.(`Routing: provider=${data.routing.FoveAI_CHAT_PROVIDER}, splice=${data.routing.FoveAI_CLOUD_SPLICE_PERCENT}%`, 'var(--neon-blue)');
                }
            } else {
                (window as any).log?.(`Brain diagnostic: HTTP ${resp.status}`, '#ff007f');
            }
        } catch (err) {
            (window as any).log?.(`Brain diagnostic fetch failed: ${err}`, '#ff007f');
        }

        // Test local brain directly
        try {
            const brain = await getLocalBrain();
            const testReply = await brain.processInput('Say OK', 'Diagnostic test');
            (window as any).log?.(`Local brain test: "${(testReply || '').substring(0, 80)}"`, testReply ? 'var(--neon-blue)' : '#ff007f');
        } catch (err) {
            (window as any).log?.(`Local brain test FAILED: ${err}`, '#ff007f');
        }
        console.log('=== END DIAGNOSTIC ===');
    };

    // --- AUDIO UNLOCK (Quest 3 / Chrome autoplay policy) ---
    // AudioContext stays suspended until a user gesture. Any click, touch, or
    // keypress will unlock it. The greeting (3s after boot) may fail silently
    // until the user interacts — this handler ensures subsequent TTS works.
    const _unlockAudioOnInteraction = () => {
        audio.unlockAudio();

        // Also pre-create/resume the shared global AudioContext under this user gesture
        const AudioContextClass = (window as any).AudioContext || (window as any).webkitAudioContext;
        if (AudioContextClass && !(window as any).foveaiAudioContext) {
            try {
                (window as any).foveaiAudioContext = new AudioContextClass();
                (window as any).foveaiAudioContext.resume();
            } catch (e) { }
        }

        document.removeEventListener('click', _unlockAudioOnInteraction);
        document.removeEventListener('touchstart', _unlockAudioOnInteraction);
        document.removeEventListener('keydown', _unlockAudioOnInteraction);
        const prompt = document.getElementById('xr-audio-prompt');
        if (prompt) prompt.style.display = 'none';
        // Retry greeting if it was generated but audio was locked (Quest 3)
        if ((window as any)._pendingGreeting) {
            videoChat.cancelSpeech();
            videoChat.speak((window as any)._pendingGreeting);
            (window as any)._pendingGreeting = null;
        }
    };
    document.addEventListener('click', _unlockAudioOnInteraction);
    document.addEventListener('touchstart', _unlockAudioOnInteraction);
    document.addEventListener('keydown', _unlockAudioOnInteraction);

    // Helper function to capture a clean JPG snapshot from any camera inside WebXR using offline WebGLRenderTarget
    function captureSnapshotFromCamera(camera: THREE.Camera): string | null {
        if (!env || !env.renderer) return null;
        const size = 1024;
        const renderTarget = new THREE.WebGLRenderTarget(size, size, {
            minFilter: THREE.LinearFilter,
            magFilter: THREE.LinearFilter,
            format: THREE.RGBAFormat
        });

        const originalTarget = env.renderer.getRenderTarget();
        const wasXREnabled = env.renderer.xr.enabled;

        try {
            env.renderer.xr.enabled = false;
            env.renderer.setRenderTarget(renderTarget);
            env.renderer.render(env.scene, camera);

            const buffer = new Uint8Array(size * size * 4);
            env.renderer.readRenderTargetPixels(renderTarget, 0, 0, size, size, buffer);

            // Restore original render target & XR state
            env.renderer.setRenderTarget(originalTarget);
            env.renderer.xr.enabled = wasXREnabled;
            renderTarget.dispose();

            const helperCanvas = document.createElement('canvas');
            helperCanvas.width = size;
            helperCanvas.height = size;
            const ctx = helperCanvas.getContext('2d');
            if (ctx) {
                const clampedBuffer = new Uint8ClampedArray(buffer.buffer);
                const imgData = new ImageData(clampedBuffer, size, size);

                const tempCanvas = document.createElement('canvas');
                tempCanvas.width = size;
                tempCanvas.height = size;
                tempCanvas.getContext('2d')!.putImageData(imgData, 0, 0);

                ctx.scale(1, -1);
                ctx.drawImage(tempCanvas, 0, -size);
                return helperCanvas.toDataURL('image/jpeg', 0.8);
            }
        } catch (err) {
            console.error('[XR] Snapshot WebGL read failed:', err);
            env.renderer.xr.enabled = wasXREnabled;
            env.renderer.setRenderTarget(originalTarget);
            if (renderTarget) renderTarget.dispose();
        }
        return null;
    }

    function triggerUserSnapshot() {
        if (!env) return;
        dashboard.log('[XR] Triggering User Viewpoint Snapshot', 'var(--neon-blue)');

        // Camera flash effect
        const flash = document.getElementById('xr-snapshot-flash');
        if (flash) { flash.style.opacity = '0.6'; setTimeout(() => { flash.style.opacity = '0'; }, 150); }

        try {
            let dataUrl = captureSnapshotFromCamera(env.camera);
            // Fallback to traditional canvas method if WebGL read failed
            if (!dataUrl) {
                const wasXREnabled = env.renderer.xr.enabled;
                env.renderer.xr.enabled = false;
                env.renderer.render(env.scene, env.camera);
                dataUrl = env.renderer.domElement.toDataURL('image/jpeg', 0.8);
                env.renderer.xr.enabled = wasXREnabled;
            }

            // Save to device outside VR
            if (!(window as any).xrSession) {
                const link = document.createElement('a');
                link.download = `foveai_user_${Date.now()}.jpg`;
                link.href = dataUrl;
                link.click();
                dashboard.log('[XR] User snapshot saved to device', '#39ff14');
            } else {
                dashboard.log('[XR] User snapshot uploaded to chat feed directly', '#39ff14');
            }

            dashboard.addMessage('user', '[SNAP] [Snapshot shared from viewpoint]', true, dataUrl);

            (async () => {
                try {
                    const base64Data = dataUrl.split(',')[1];
                    const attachments = [{
                        name: `snapshot_user_${Date.now()}.jpg`,
                        type: 'image' as const,
                        mediaType: 'image/jpeg',
                        base64: base64Data
                    }];
                    const soulReply = await fetchSoulFallback(
                        "The user shared a snapshot from their XR viewpoint. Describe what you see in the snapshot warmly and comment on it briefly.",
                        "Snapshot Shared",
                        false, // deepThought
                        (window as any).foveaiDashboard?.privacyMode || false, // privacyMode
                        attachments
                    );
                    const replyText = soulReply || "I see you've shared a snapshot! What are you looking at?";
                    dashboard.addMessage('assistant', replyText);
                    videoChat.speak(replyText);
                } catch (err) {
                    dashboard.log(`Snapshot response error: ${err}`, '#ff007f');
                }
            })();
        } catch (e) {
            dashboard.log('[XR] User snapshot failed', '#ff007f');
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // ── "Be Jen" First-Person POV Mode ──
    // Renders the scene from Jen's head bone perspective every frame,
    // so you experience the world as if you were Jen looking out through
    // her eyes. Toggle with the V key, SoftLayer param, or tray menu.
    // ═══════════════════════════════════════════════════════════════
    let jenPovCamera: THREE.PerspectiveCamera | null = null;
    let jenPovActive = false;
    const _jenPovHeadPos = new THREE.Vector3();
    const _jenPovHeadQuat = new THREE.Quaternion();
    const _jenPovEyeOffset = new THREE.Vector3(0, 0.05, 0.08); // slight forward+up from head bone center

    function getJenPovCamera(): THREE.PerspectiveCamera | null {
        if (!env) return null;
        if (!jenPovCamera) {
            jenPovCamera = new THREE.PerspectiveCamera(
                70, // slightly wider FOV for immersive feel
                env.renderer.domElement.width / env.renderer.domElement.height,
                0.05, 100
            );
            jenPovCamera.layers.enable(0);
            jenPovCamera.layers.enable(1); // see Layer 1 objects (desktop screen, user avatar)
        }
        return jenPovCamera;
    }

    function updateJenPovCamera() {
        if (!jenPovCamera || !avatar || !avatar.vrm) return;
        const headBone = avatar.vrm.humanoid?.getNormalizedBoneNode('head');
        if (headBone) {
            headBone.getWorldPosition(_jenPovHeadPos);
            headBone.getWorldQuaternion(_jenPovHeadQuat);
        } else {
            _jenPovHeadPos.copy(avatar.vrm.scene.position);
            _jenPovHeadPos.y += 1.3;
            _jenPovHeadQuat.copy(avatar.vrm.scene.quaternion);
        }
        // Apply small eye offset in head-local space (forward + slightly up)
        const offsetWorld = _jenPovEyeOffset.clone().applyQuaternion(_jenPovHeadQuat);
        jenPovCamera.position.copy(_jenPovHeadPos).add(offsetWorld);
        jenPovCamera.quaternion.copy(_jenPovHeadQuat);
    }

    function setJenPovMode(active: boolean) {
        jenPovActive = active;
        (window as any).foveaiJenPovActive = active;
        if (active) {
            getJenPovCamera(); // ensure camera exists
            dashboard.log('[XR] 🧑 Be Jen mode: ON — you are now looking through Jen\'s eyes', 'var(--neon-pink)');
        } else {
            dashboard.log('[XR] 🧑 Be Jen mode: OFF — returning to user camera', 'var(--neon-blue)');
        }
    }

    function toggleJenPovMode() {
        setJenPovMode(!jenPovActive);
    }

    (window as any).foveaiToggleJenPov = toggleJenPovMode;
    (window as any).foveaiSetJenPov = setJenPovMode;

    // Keyboard shortcut: V to toggle "Be Jen" mode, M to toggle Avalanche music
    window.addEventListener('keydown', (e: KeyboardEvent) => {
        // Ignore if typing in an input/textarea
        const target = e.target as HTMLElement;
        if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
        if (e.key === 'v' || e.key === 'V') {
            toggleJenPovMode();
        } else if (e.key === 'm' || e.key === 'M') {
            const playing = directorVoice.toggleAvalancheMusic();
            dashboard.log(`[Director] 🎵 Avalanche music: ${playing ? 'ON' : 'OFF'}`, '#8a7a5a');
        }
    });

    function triggerAvatarSnapshot() {
        if (!env) return;
        dashboard.log('[XR] Triggering Avatar Head Viewpoint Snapshot', 'var(--neon-blue)');

        // Camera flash effect
        const flash = document.getElementById('xr-snapshot-flash');
        if (flash) { flash.style.opacity = '0.6'; setTimeout(() => { flash.style.opacity = '0'; }, 150); }

        try {
            const avatarCam = new THREE.PerspectiveCamera(
                60,
                env.renderer.domElement.width / env.renderer.domElement.height,
                0.1, 100
            );
            avatarCam.layers.enable(1);
            if (avatar && avatar.vrm) {
                const headBone = avatar.vrm.humanoid.getNormalizedBoneNode('head');
                if (headBone) {
                    headBone.getWorldPosition(avatarCam.position);
                    headBone.getWorldQuaternion(avatarCam.quaternion);
                } else {
                    avatarCam.position.copy(avatar.vrm.scene.position);
                    avatarCam.position.y += 0.3;
                    avatarCam.quaternion.copy(avatar.vrm.scene.quaternion);
                }
            }

            let dataUrl = captureSnapshotFromCamera(avatarCam);
            if (!dataUrl) {
                const wasXREnabled = env.renderer.xr.enabled;
                env.renderer.xr.enabled = false;
                env.renderer.render(env.scene, avatarCam);
                dataUrl = env.renderer.domElement.toDataURL('image/jpeg', 0.8);
                env.renderer.xr.enabled = wasXREnabled;
            }

            if (!(window as any).xrSession) {
                const link = document.createElement('a');
                link.download = `foveai_avatar_${Date.now()}.jpg`;
                link.href = dataUrl;
                link.click();
                dashboard.log('[XR] Avatar snapshot saved to device', '#39ff14');
            } else {
                dashboard.log('[XR] Avatar snapshot uploaded to chat feed directly', '#39ff14');
            }

            // Restore main rendering viewpoint context
            env.renderer.render(env.scene, env.camera);

            // Send avatar snapshot message from Jen!
            (async () => {
                try {
                    const base64Data = dataUrl!.split(',')[1];
                    const attachments = [{
                        name: `snapshot_avatar_${Date.now()}.jpg`,
                        type: 'image' as const,
                        mediaType: 'image/jpeg',
                        base64: base64Data
                    }];
                    const soulReply = await fetchSoulFallback(
                        "You just took a snapshot from your own head viewpoint (looking at the user or the room). Describe what you captured from your perspective and share it warmly.",
                        "Avatar Snapshot Captured",
                        false, // deepThought
                        (window as any).foveaiDashboard?.privacyMode || false, // privacyMode
                        attachments
                    );
                    const replyText = soulReply || "I just took a quick snapshot from my perspective! Let me know if you like it! <audio:chuckle_warm>";
                    dashboard.addMessage('assistant', replyText, true, dataUrl);
                    videoChat.speak(replyText);
                } catch (err) {
                    dashboard.log(`Avatar snapshot response error: ${err}`, '#ff007f');
                    dashboard.addMessage('assistant', "I just took a quick snapshot from my perspective! Let me know if you like it! <audio:chuckle_warm>", true, dataUrl);
                }
            })();
        } catch (e) {
            dashboard.log('[XR] Avatar snapshot failed', '#ff007f');
        }
    }

    // Voice snapshot trigger listener
    window.addEventListener('foveai_voice_snapshot', (e: any) => {
        const text = (e.detail?.text || '').toLowerCase();
        const isWebcamSnapshot = text.includes('webcam') || text.includes('camera') || text.includes('real') || text.includes('physical');
        const isUserSnapshot = text.includes('my') || text.includes('user') || text.includes('me') || text.includes('my snapshot');
        const isDevSnapshot = text.includes('dev') || text.includes('developer') || text.includes('your') || text.includes('antigravity');

        if (isWebcamSnapshot) {
            triggerWebcamSnapshot();
        } else if (isUserSnapshot) {
            triggerUserSnapshot();
        } else if (isDevSnapshot) {
            triggerDeveloperSnapshot();
        } else {
            triggerAvatarSnapshot();
        }
    });

    // AI-triggered snapshot listener
    window.addEventListener('foveai_action_trigger', (e: any) => {
        const action = e.detail?.action;
        const params = e.detail?.params || {};
        if (action === 'snapshot') {
            const type = params.type || 'quest';
            triggerImmediateSnapshot(type);
        }
    });

    // Feedback Loop Listeners: inject silent system context back to Soul
    window.addEventListener('foveai_body_feedback', async (e: any) => {
        const msg = e.detail?.message;
        if (msg) {
            if (!isBrainThinking) {
                dashboard.log(`[Feedback] ${msg}`, 'var(--neon-green)');
                await fetchSoulFallback(`[SYSTEM FEEDBACK] ${msg}\n(You may briefly and naturally react to this out loud in character if you wish, or simply adapt your internal context.)`, "System Feedback", false, true);
            } else {
                dashboard.log(`[Feedback QUEUED] ${msg}`, 'var(--neon-blue)');
                systemFeedbackQueue.push(msg);
            }
        }
    });

    window.addEventListener('foveai_action_result', async (e: any) => {
        const msg = e.detail?.message;
        if (msg) {
            if (!isBrainThinking) {
                dashboard.log(`[Action Result] ${msg}`, 'var(--neon-green)');
                await fetchSoulFallback(`[SYSTEM FEEDBACK] ${msg}\n(You may briefly and naturally react to this out loud in character if you wish, or simply adapt your internal context.)`, "System Feedback", false, true);
            } else {
                dashboard.log(`[Action QUEUED] ${msg}`, 'var(--neon-blue)');
                systemFeedbackQueue.push(msg);
            }
        }
    });

    function triggerImmediateSnapshot(type: string) {
        if (!env) return;
        dashboard.log(`[XR] AI Request: Snapshot type=${type}`, 'var(--neon-blue)');

        const flash = document.getElementById('xr-snapshot-flash');
        if (flash) { flash.style.opacity = '0.6'; setTimeout(() => { flash.style.opacity = '0'; }, 150); }

        try {
            let dataUrl: string | null = null;
            if (type === 'webcam') {
                const videoEl = (window as any).foveaiPortalVideo as HTMLVideoElement | null;
                if (videoEl && videoEl.readyState >= 2) {
                    const canvas = document.createElement('canvas');
                    canvas.width = videoEl.videoWidth || 640;
                    canvas.height = videoEl.videoHeight || 360;
                    const ctx = canvas.getContext('2d');
                    if (ctx) {
                        ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
                        dataUrl = canvas.toDataURL('image/jpeg', 0.85);
                    }
                }
            } else if (type === 'quest') {
                const xrCamera = env.renderer.xr.enabled && env.renderer.xr.isPresenting ? env.renderer.xr.getCamera() : undefined;
                const activeCam = xrCamera || env.camera;
                dataUrl = captureSnapshotFromCamera(activeCam);
                if (!dataUrl) {
                    const wasXREnabled = env.renderer.xr.enabled;
                    env.renderer.xr.enabled = false;
                    env.renderer.render(env.scene, activeCam);
                    dataUrl = env.renderer.domElement.toDataURL('image/jpeg', 0.8);
                    env.renderer.xr.enabled = wasXREnabled;
                }
            } else { // composite
                const xrCamera = env.renderer.xr.enabled && env.renderer.xr.isPresenting ? env.renderer.xr.getCamera() : undefined;
                const composite = getCompositeVision();
                const wasXREnabled = env.renderer.xr.enabled;
                env.renderer.xr.enabled = false;
                env.renderer.render(env.scene, env.camera);
                const avatarFrame = env.renderer.domElement.toDataURL('image/jpeg', 0.8);
                const avatarBase64 = avatarFrame.split(',')[1] || avatarFrame;
                env.renderer.xr.enabled = wasXREnabled;

                let webcamBase64: string | null = null;
                const videoEl = (window as any).foveaiPortalVideo as HTMLVideoElement | null;
                if (videoEl && videoEl.readyState >= 2) {
                    const canvas = document.createElement('canvas');
                    canvas.width = videoEl.videoWidth || 640;
                    canvas.height = videoEl.videoHeight || 360;
                    const ctx = canvas.getContext('2d');
                    if (ctx) {
                        ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
                        webcamBase64 = canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
                    }
                }

                let passthroughBase64: string | null = null;
                const compositeVisionObj = getCompositeVision();
                if ((compositeVisionObj as any).passthroughVideo && (compositeVisionObj as any).passthroughCtx && (compositeVisionObj as any).passthroughCanvas) {
                    try {
                        (compositeVisionObj as any).passthroughCtx.drawImage((compositeVisionObj as any).passthroughVideo, 0, 0, 640, 360);
                        passthroughBase64 = (compositeVisionObj as any).passthroughCanvas.toDataURL('image/jpeg', 0.7).split(',')[1] || null;
                    } catch {}
                }

                const compositeBase64 = (composite as any).buildComposite(avatarBase64, webcamBase64, passthroughBase64);
                dataUrl = 'data:image/jpeg;base64,' + compositeBase64;
            }

            if (dataUrl) {
                dashboard.addMessage('assistant', `[SNAPSHOT] Here is the on-demand ${type} view.`, true, dataUrl);
                videoChat.speak(`Here is the requested ${type} camera capture.`);
            } else {
                dashboard.log(`[XR] AI snapshot failed: source for "${type}" offline`, '#ffaa00');
            }
        } catch (e) {
            dashboard.log(`[XR] AI snapshot failed: ` + e, '#ff007f');
        }
    }

    function triggerWebcamSnapshot() {
        const videoEl = (window as any).foveaiPortalVideo as HTMLVideoElement | null;
        if (!videoEl || videoEl.readyState < 2) {
            dashboard.log('[XR] Webcam is not ready or not active.', '#ffaa00');
            return;
        }
        dashboard.log('[XR] Triggering Physical Webcam Snapshot', 'var(--neon-blue)');

        // Camera flash effect
        const flash = document.getElementById('xr-snapshot-flash');
        if (flash) { flash.style.opacity = '0.6'; setTimeout(() => { flash.style.opacity = '0'; }, 150); }

        try {
            const canvas = document.createElement('canvas');
            canvas.width = videoEl.videoWidth || 640;
            canvas.height = videoEl.videoHeight || 360;
            const ctx = canvas.getContext('2d');
            if (ctx) {
                ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
                const dataUrl = canvas.toDataURL('image/jpeg', 0.85);

                dashboard.addMessage('user', '[WEBCAM] [Webcam snapshot shared]', true, dataUrl);

                (async () => {
                    try {
                        const base64Data = dataUrl.split(',')[1];
                        const attachments = [{
                            name: `snapshot_webcam_${Date.now()}.jpg`,
                            type: 'image' as const,
                            mediaType: 'image/jpeg',
                            base64: base64Data
                        }];
                        const soulReply = await fetchSoulFallback(
                            "The user shared a snapshot from their physical webcam feed. Describe what you see in the room or of the user warmly, noting details from their actual environment.",
                            "Webcam Snapshot Shared",
                            false, // deepThought
                            (window as any).foveaiDashboard?.privacyMode || false, // privacyMode
                            attachments
                        );
                        const replyText = soulReply || "I see you via your webcam! It's great to see your real room and environment.";
                        dashboard.addMessage('assistant', replyText);
                        videoChat.speak(replyText);
                    } catch (err) {
                        dashboard.log(`Webcam snapshot response error: ${err}`, '#ff007f');
                    }
                })();
            } else {
                dashboard.log('[XR] Failed to get canvas 2d context for webcam snapshot', '#ff007f');
            }
        } catch (e) {
            dashboard.log('[XR] Webcam snapshot failed: ' + e, '#ff007f');
        }
    }

    function triggerDeveloperSnapshot() {
        if (!env) return;
        dashboard.log('[XR] Triggering Developer Viewpoint Snapshot (1m right of User)', 'var(--neon-blue)');

        // Camera flash effect
        const flash = document.getElementById('xr-snapshot-flash');
        if (flash) { flash.style.opacity = '0.6'; setTimeout(() => { flash.style.opacity = '0'; }, 150); }

        try {
            const devCam = new THREE.PerspectiveCamera(
                60,
                env.renderer.domElement.width / env.renderer.domElement.height,
                0.1, 100
            );
            devCam.layers.enable(0);
            devCam.layers.enable(1); // Enable both layers so we see user POV + virtual avatars

            const userPos = new THREE.Vector3();
            const userQuat = new THREE.Quaternion();
            env.camera.getWorldPosition(userPos);
            env.camera.getWorldQuaternion(userQuat);

            // Position 1m to the right relative to user head rotation
            const rightVec = new THREE.Vector3(1, 0, 0).applyQuaternion(userQuat);
            devCam.position.copy(userPos).addScaledVector(rightVec, 1.0);

            // Look at a target point 1.2m in front of the user (e.g. where the HUD floats)
            const forwardVec = new THREE.Vector3(0, 0, -1).applyQuaternion(userQuat);
            const lookTarget = new THREE.Vector3().copy(userPos).addScaledVector(forwardVec, 1.2);
            devCam.lookAt(lookTarget);

            let dataUrl = captureSnapshotFromCamera(devCam);
            if (!dataUrl) {
                const wasXREnabled = env.renderer.xr.enabled;
                env.renderer.xr.enabled = false;
                env.renderer.render(env.scene, devCam);
                dataUrl = env.renderer.domElement.toDataURL('image/jpeg', 0.8);
                env.renderer.xr.enabled = wasXREnabled;
            }

            if (!(window as any).xrSession) {
                const link = document.createElement('a');
                link.download = `foveai_developer_${Date.now()}.jpg`;
                link.href = dataUrl;
                link.click();
                dashboard.log('[XR] Developer snapshot saved to device', '#39ff14');
            } else {
                dashboard.log('[XR] Developer snapshot uploaded directly', '#39ff14');
            }

            // Restore main rendering viewpoint context
            env.renderer.render(env.scene, env.camera);

            // Send developer snapshot message
            (async () => {
                try {
                    const base64Data = dataUrl!.split(',')[1];
                    const attachments = [{
                        name: `snapshot_developer_${Date.now()}.jpg`,
                        type: 'image' as const,
                        mediaType: 'image/jpeg',
                        base64: base64Data
                    }];
                    const soulReply = await fetchSoulFallback(
                        "You just took a snapshot from your Developer viewpoint (1m right of the user, tilted left looking at their HUD/playspace). Describe what you see in the scene and HUD from this perspective.",
                        "Developer Snapshot Captured",
                        false,
                        (window as any).foveaiDashboard?.privacyMode || false,
                        attachments
                    );
                    const replyText = soulReply || "Here is what I see from my developer viewport! Looking good.";
                    dashboard.addMessage('assistant', replyText, true, dataUrl);
                    videoChat.speak(replyText);
                } catch (err) {
                    dashboard.log(`Dev snapshot response error: ${err}`, '#ff007f');
                    dashboard.addMessage('assistant', "Here is what I see from my developer viewport! Looking good.", true, dataUrl);
                }
            })();
        } catch (e) {
            dashboard.log('[XR] Developer snapshot failed', '#ff007f');
        }
    }
