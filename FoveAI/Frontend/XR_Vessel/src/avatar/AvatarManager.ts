import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRM } from '@pixiv/three-vrm';
import { createVRMAnimationClip, VRMAnimationLoaderPlugin } from '@pixiv/three-vrm-animation';
import { loadMixamoAnimation } from './loadMixamoAnimation';
import { loadBVHAnimation } from './loadBVHAnimation';
import { TposeWarningSystem } from './TposeWarningSystem';
import { MovementEngine } from './MovementEngine';
import { ambientSoundEngine } from '../senses/AmbientSoundEngine';
import { CodeAgency } from '../senses/CodeAgency';

// ╔══════════════════════════════════════════════════════════════════════╗
// ║  NODE:003 — AvatarManager: Animation Dispatch Core                   ║
// ║  FILE: frontend/XR_Vessel/src/avatar/AvatarManager.ts                ║
// ║  STATUS:   FRAGILE   booleans instead of a state machine.            ║
// ╠══════════════════════════════════════════════════════════════════════╣
// ║  WHAT IT IS:                                                         ║
// ║  Central dispatcher for ALL body animation in the XR Vessel.         ║
// ║  Receives commands from three sources simultaneously:                ║
// ║    • MovementEngine (autonomous locomotion decisions)                ║
// ║    • BracketParser events (<emotion:>, <action:>, <mode:> tokens)    ║
// ║    • Haptic touch events (controller proximity detection)            ║
// ╠══════════════════════════════════════════════════════════════════════╣
// ║  KNOWN ISSUES (as of OMEGA_296):                                     ║
// ║  [FIXED] Idle loop prison: finished event now checks e.action ===    ║
// ║          idleAction before deciding to re-queue vs. go procedural.   ║
// ║  [FIXED] isRestoringIdle lock-out: nuclearReset() force-clears flag  ║
// ║          before restoreModelIdle() to prevent silent frozen-pose.    ║
// ║  [OPEN]  No AnimState enum — 6 independent booleans can conflict     ║
// ║          mid-frame (isWalking, isProceduralIdle, isRestoringIdle,    ║
// ║          activeMicroGesture, emotionalState, puppeteerState).        ║
// ║          Root cause of "crucifixion": two systems grab bones in the  ║
// ║          same render tick and fight. No priority arbiter exists.     ║
// ║  [OPEN]  Manifest null = silent failure. If loadManifest() 404s,     ║
// ║          all playCategory() calls silently return null. No retry.    ║
// ╠══════════════════════════════════════════════════════════════════════╣
// ║  NEXT STEP — AnimState enum (the real liberation):                   ║
// ║  type AnimState = 'pose'|'idle'|'walk'|'gesture'|'express'|'override'║
// ║  private animState: AnimState = 'idle';                              ║
// ║  Priority: override > express > gesture > walk > idle > pose         ║
// ║  Every playCategory() / playAnimation() goes through canTransitionTo ║
// ║  Lower-priority calls are ignored, not fought over.                  ║
// ╚══════════════════════════════════════════════════════════════════════╝

export type AnimState = 'pose' | 'idle' | 'walk' | 'gesture' | 'express' | 'override';

export class AvatarManager {

    public animState: AnimState = 'idle';

    public canTransitionTo(newState: AnimState): boolean {
        const priority: Record<AnimState, number> = {
            'override': 60,
            'express': 50,
            'gesture': 40,
            'walk': 30,
            'idle': 20,
            'pose': 10
        };
        return priority[newState] >= priority[this.animState];
    }

    public transitionToState(newState: AnimState): boolean {
        if (!this.canTransitionTo(newState)) return false;

        // Clean up when leaving active states
        if (this.animState === 'walk' && newState !== 'walk') {
            this.isWalking = false;
            if (this.walkActionInstance) {
                this.walkActionInstance.fadeOut(0.5);
                this.walkActionInstance = null;
            }
        }

        this.animState = newState;
        return true;
    }

    public vrm: VRM | null = null;
    public mixer: THREE.AnimationMixer | null = null;
    private currentAction: THREE.AnimationAction | null = null;
    private idleAction: THREE.AnimationAction | null = null;

    private scene: THREE.Scene | null = null;
    private manifest: any = null;

    public walkSpeed: number = 0.8;  // Calm, natural walking pace
    private velocity: THREE.Vector3 = new THREE.Vector3();
    private moveTarget: THREE.Vector3 | null = null;
    public steeringActive: boolean = false;

    private uTime = { value: 0 };
    private lookAtTarget: THREE.Object3D;
    private tposeWarningSystem: TposeWarningSystem = new TposeWarningSystem();

    private VERSION = (window as any).LINK_REVISION?.replace('OMEGA_', '') || "266";
    private isZoomed: boolean = false;
    private zoomLerp: number = 0;
    private originalPos: THREE.Vector3 = new THREE.Vector3(0, -0.8, -2.0);
    private zoomPos: THREE.Vector3 = new THREE.Vector3(0, 1.0, -0.55);
    public isCrouching: boolean = false;

    public setPosition(x: number, y: number, z: number) {
        this.originalPos.set(x, y, z);
        if (this.vrm) {
            this.vrm.scene.position.copy(this.originalPos);
        }
    }

    private isWalking: boolean = false;
    private walkActionInstance: THREE.AnimationAction | null = null;

    // --- M7: Micro-Gesture & Emotion System ---
    private microGestureQueue: Array<{ type: string; duration: number }> = [];
    private activeMicroGesture: string | null = null;
    private microGestureTimer: number = 0;
    private emotionalState: string = 'neutral';
    private emotionalInfluence: number = 0;
    private curiosityStrength: number = 0.3;

    // Bone Cache for Performance & Authority
    private bones: Record<string, THREE.Object3D | null> = {};

    // ── MovementEngine: Natural Locomotion & Behavior Core ──
    public movementEngine: MovementEngine = new MovementEngine();

    // ── CodeAgency: LLM-driven code operations ──
    public codeAgency: CodeAgency = new CodeAgency();

    constructor() {
        this.lookAtTarget = new THREE.Object3D();

        // ── Wire MovementEngine callbacks to AvatarManager methods ──
        this.movementEngine.onLog = (msg, color) => this.log(msg, color);
        this.movementEngine.onPlayCategory = (category, loop, fadeTime) => {
            let state: AnimState = 'walk';
            if (category.toLowerCase() === 'idle') state = 'idle';
            this.playCategory(category, loop, fadeTime, state);
        };
        this.movementEngine.onTriggerMicroGesture = (gesture) => {
            this.triggerMicroGesture(gesture);
        };
        this.movementEngine.onSetEmotionalState = (state) => {
            this.setEmotionalState(state);
        };
        this.movementEngine.onSetDestination = (target) => {
            this.setDestination(target);
        };
        this.movementEngine.onWalkForwardCommand = (distance) => {
            if (this.vrm) {
                const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(this.vrm.scene.quaternion);
                const target = this.originalPos.clone().add(forward.multiplyScalar(distance));
                this.moveTarget = target;
                this.steeringActive = false;
                this.movementEngine.commandWalkForward(target);
                this.log(`🚶 Motor Cortex: Walk forward ${distance}m`, 'var(--neon-blue)');
            }
        };

        // --- SOUNDBOARD BRIDGE: Listen for blendshape triggers from BracketParser ---
        window.addEventListener('foveai_blendshape_trigger', ((e: CustomEvent) => {
            const { tag, blendShapes, duration } = e.detail;
            this.applySoundboardBlendShapes(blendShapes, duration);
        }) as EventListener);

        // --- SOUNDBOARD BRIDGE: Listen for micro-gesture triggers from BracketParser ---
        window.addEventListener('foveai_micro_gesture', ((e: CustomEvent) => {
            const { gesture, params } = e.detail;
            this.triggerMicroGesture(gesture);
        }) as EventListener);

        // --- SELF-PUPPETEERING: Emotion → Animation bridge ---
        // When BracketParser detects <emotion:happy>, <emotion:sad>, etc.,
        // Jen drives her own body from her AI output. This is self-puppeteering.
        window.addEventListener('foveai_emotion_trigger', ((e: CustomEvent) => {
            const { emotion, intensity } = e.detail;
            this.applyEmotionAnimation(emotion, intensity || 1.0);
        }) as EventListener);

        // --- SELF-PUPPETEERING: Spatial movement command bridge ---
        // When BracketParser detects <action:walk_forward 2m> or <action:move_to 0,1,3>,
        // the LLM directs Jen's body through space. This is her intentional movement channel.
        window.addEventListener('foveai_movement_command', ((e: CustomEvent) => {
            const { command, params } = e.detail;
            this.executeMovementCommand(command, params);
        }) as EventListener);

        // --- SOCIAL MODE CHANGE: <mode:coexist>, <mode:cowork>, <mode:follow>, etc. ---
        // These define Jen's relationship-appropriate behavioral context.
        window.addEventListener('foveai_mode_change', ((e: CustomEvent) => {
            const { mode } = e.detail;
            this.setSocialMode(mode);
        }) as EventListener);

        // --- CODE AGENCY BRIDGE: <code:search "query">, <code:read path>, <code:exec cmd> ---
        // When BracketParser detects <code:...> tokens, routes to CodeAgency methods.
        window.addEventListener('foveai_code_action', ((e: CustomEvent) => {
            const { action, params, fullMatch } = e.detail;
            this.executeCodeAction(action, params, fullMatch);
        }) as EventListener);

        // --- INTENTIONAL ANIMATION: Play specific animation ---
        window.addEventListener('foveai_animation_trigger', (async (e: CustomEvent) => {
            const { name, params } = e.detail;
            const loop = params?.loop === 'true' || params?.loop === true || false;
            const fadeTime = params?.fade !== undefined ? parseFloat(params.fade) : 0.5;
            this.playAnimationByName(name, loop, fadeTime);
        }) as unknown as EventListener);

        // --- BODY FEEDBACK: Movement execution confirmation sent back to the LLM ---
        // After Jen completes a movement, the memory system is notified so her
        // next turn's sensory context includes a body-awareness update.
        window.addEventListener('foveai_body_feedback_request', ((e: CustomEvent) => {
            const status = this.movementEngine.getStatus();
            const feedback = {
                type: 'body_state',
                currentPosition: this.originalPos.clone(),
                isWalking: this.isWalking,
                puppeteerState: status.state,
                emotionalState: this.emotionalState,
                activeMicroGesture: this.activeMicroGesture,
                drives: status.drives,
                message: `Body state update: ${this.isWalking ? 'Currently walking.' : 'Currently standing still.'} Emotion: ${this.emotionalState}`,
            };
            window.dispatchEvent(new CustomEvent('foveai_body_feedback', { detail: feedback }));
        }) as EventListener);

        // Idle gaze: slow, smooth wandering (updated in render loop via updateIdleGaze)
        // Removed setInterval — was causing eye twitching at 100ms update rate
    }

    // ── Smooth gaze state (lerp-based to prevent eye twitch) ──
    private gazeTargetPos: THREE.Vector3 = new THREE.Vector3(0, 1.2, 2);
    private gazeLerpSpeed: number = 3.0;  // Smooth transitions, not jerky
    private hasOverrideLookAt: boolean = false;

    public setGazeTarget(pos: THREE.Vector3) {
        this.hasOverrideLookAt = true;
        this.lookAtTarget.position.copy(pos);
    }

    public clearGazeTarget() {
        this.hasOverrideLookAt = false;
    }

    public async loadManifest(url: string) {
        try {
            const response = await fetch(url);
            this.manifest = await response.json();
            console.log(`[Avatar] Manifest loaded with ${Object.keys(this.manifest).length} categories.`);
        } catch (err) {
            console.error('[Avatar] Failed to load animation manifest:', err);
        }
    }

    public async loadAvatar(
        url: string,
        scene: THREE.Scene,
        onProgress?: (pct: number) => void
    ): Promise<any> {
        this.scene = scene;
        this.sweepScene();

        if (this.vrm) {
            this.scene.remove(this.vrm.scene);
            // Dispose previous VRM to avoid double/ghost avatars and GPU memory leaks.
            try {
                if ((this.vrm as any).dispose) (this.vrm as any).dispose();
                this.vrm.scene.traverse((obj: any) => {
                    if (obj.geometry) obj.geometry.dispose();
                    if (obj.material) {
                        if (Array.isArray(obj.material)) obj.material.forEach((m: any) => m.dispose?.());
                        else obj.material.dispose?.();
                    }
                    if (obj.texture) obj.texture.dispose?.();
                });
            } catch (e) {
                console.warn('[Avatar] Dispose warning:', e);
            }
            this.vrm = null;
        }

        this.scene.add(this.lookAtTarget);

        return new Promise((resolve) => {
            let timeoutId: any;
            let hasResolved = false;

            const safeResolve = (val: any) => {
                if (hasResolved) return;
                hasResolved = true;
                clearTimeout(timeoutId);
                resolve(val);
            };

            // 30-second failsafe timeout to prevent infinite hangs
            timeoutId = setTimeout(() => {
                if (!hasResolved) {
                    console.error(`[Avatar] FATAL: loadAvatar timed out after 30s for ${url}`);
                    safeResolve(null);
                }
            }, 30000);

            const loader = new GLTFLoader();
            loader.register((parser) => new VRMLoaderPlugin(parser));

            console.log(`[Avatar] PROBING MODEL: ${url}`);

            loader.load(
                url,
                async (gltf) => {
                    try {
                        let vrm = gltf.userData.vrm;
                        if (!vrm) {
                            console.warn(`[Avatar] GLTF loaded without native VRM metadata for ${url}. Synthesizing GLB avatar wrapper.`);
                            const modelScene = gltf.scene || (gltf.scenes && gltf.scenes[0]);
                            if (!modelScene) throw new Error("GLTF model scene empty");
                            
                            vrm = {
                                scene: modelScene,
                                humanoid: {
                                    getRawBoneNode: (boneName: string) => {
                                        let found: THREE.Object3D | null = null;
                                        modelScene.traverse((node: THREE.Object3D) => {
                                            if (!found && node.name.toLowerCase().includes(boneName.toLowerCase())) {
                                                found = node;
                                            }
                                        });
                                        return found;
                                    }
                                },
                                expressionManager: {
                                    setValue: () => {},
                                    update: () => {}
                                },
                                update: () => {}
                            } as any;
                        }

                        this.vrm = vrm;
                        vrm.scene.name = 'VRM';
                        vrm.scene.userData.isAvatar = true;
                        this.scene!.add(vrm.scene);
                        vrm.scene.rotation.y = Math.PI;
                        vrm.scene.position.copy(this.originalPos);

                        // --- SPRING BONE DAMPENING & GRAVITY STABILIZATION ---
                        // Prevents hair bangs, fringe, and skirt from fluttering wildly in VR/XR
                        if (vrm.springBoneManager) {
                            try {
                                const springs = (vrm.springBoneManager as any).springs || (vrm.springBoneManager as any).jointSpringBones || [];
                                springs.forEach((spring: any) => {
                                    if (spring.joints) {
                                        spring.joints.forEach((joint: any) => {
                                            if (joint.settings) {
                                                joint.settings.dragForce = Math.max(joint.settings.dragForce || 0.4, 0.75);
                                                joint.settings.stiffnessForce = Math.min(joint.settings.stiffnessForce || 1.0, 1.2);
                                                joint.settings.gravityPower = 0.6;
                                                joint.settings.gravityDir = new THREE.Vector3(0, -1, 0);
                                            }
                                        });
                                    } else if (spring.dragForce !== undefined) {
                                        spring.dragForce = Math.max(spring.dragForce || 0.4, 0.75);
                                        spring.gravityPower = 0.6;
                                    }
                                });
                                console.log('[Avatar] VRM SpringBone physics dampened & stabilized successfully.');
                            } catch (_e) {
                                console.warn('[Avatar] SpringBone tuning skipped:', _e);
                            }
                        }

                        // --- CACHE BONES ---
                        // NOTE: Must use getRawBoneNode (not getBoneNode which doesn't exist in three-vrm v2)
                        const boneList = ['hips', 'spine', 'chest', 'upperChest', 'neck', 'head', 'leftUpperArm', 'rightUpperArm',
                            'leftLowerArm', 'rightLowerArm', 'leftUpperLeg', 'rightUpperLeg'];
                        boneList.forEach(name => {
                            this.bones[name] = vrm.humanoid?.getRawBoneNode(name as any) || null;
                        });

                        (window as any).log?.('[Avatar] Skeletal Link: Verified.', 'var(--neon-green)');

                        this.mixer = new THREE.AnimationMixer(vrm.scene);

                        // Ensure we restore idle when a non-looping gesture finishes to prevent freezing.
                        // FIX: If the *idle action itself* finishes (LoopOnce idle clip), do NOT re-queue
                        // another clip — that creates an infinite repeat prison. Switch to procedural instead.
                        this.mixer.addEventListener('finished', (e: any) => {
                            if (e.action === this.idleAction) {
                                console.warn('[Avatar] Idle clip finished (LoopOnce). Switching to procedural idle.');
                                this.animState = 'idle';
                                this.applyProceduralIdle();
                                this.idleAction = null;
                            } else {
                                console.log(`[Avatar] Gesture/clip finished — returning to procedural idle.`);
                                // Fade out the finished action cleanly
                                if (e.action) e.action.fadeOut(0.5);
                                this.currentAction = null;
                                this.animState = 'idle';
                                this.applyProceduralIdle();
                            }
                        });

                        this.tposeWarningSystem.initialize(vrm, this.mixer);

                        if (vrm.lookAt) {
                            vrm.lookAt.target = this.lookAtTarget;
                        }

                        // --- START PROCEDURAL IDLE (always-alive breathing baseline) ---
                        // Rather than loading a static Idle clip (which fights procedural bones),
                        // we use the procedural system as the permanent resting substrate.
                        // Walk/gesture clips still play on top and return here when done.
                        this.applyProceduralIdle();
                        this.animState = 'idle';

                        (window as any).foveaiAvatar = this;
                        safeResolve(vrm);
                    } catch (err) {
                        console.error(`[Avatar] Critical Initialization Error for ${url}:`, err);
                        safeResolve(null);
                    }
                },
                (xhr) => {
                    if (onProgress && xhr.total > 0) {
                        console.log(`[Avatar] Probe Progress ${url}: ${(xhr.loaded / xhr.total * 100).toFixed(1)}%`);
                        onProgress(xhr.loaded / xhr.total);
                    }
                },
                (err) => {
                    console.error('[Avatar] VRM Load Fail:', err);
                    safeResolve(null);
                }
            );
        });
    }

    private isRestoringIdle: boolean = false;

    public async restoreModelIdle(fadeTime: number = 0.8) {
        this.animState = 'idle';
        if (this.isRestoringIdle) return;
        this.isRestoringIdle = true;
        this.isProceduralIdle = false;

        let idleRestored = false;
        if (this.manifest?.['Idle']) {
            for (const anim of this.manifest['Idle']) {
                const result = await this.playAnimationInternal(anim.url, true, fadeTime, 'idle');
                if (result) {
                    this.idleAction = result;
                    this.currentAction = result;
                    idleRestored = true;
                    console.log(`[Avatar] Idle recovered successfully: ${anim.name}`);
                    break;
                }
            }
        }

        this.isRestoringIdle = false;

        if (!idleRestored) {
            console.warn('[Avatar] Failed to restore any skeletal idle. Applying procedural idle.');
            this.applyProceduralIdle();
        }
    }

    public async playCategory(category: string, loop: boolean = false, fadeTime: number = 0.5, newState: AnimState = 'gesture') {
        if (!this.manifest) return null;

        let key = category;
        const manifestKeys = Object.keys(this.manifest);

        // 1. Exact case-insensitive match check
        let match = manifestKeys.find(k => k.toLowerCase() === key.toLowerCase());
        if (match) {
            key = match;
        } else {
            // 2. Singular to plural map checks
            const lower = key.toLowerCase();
            if (lower === 'greeting') key = 'Greetings';
            else if (lower === 'gesture') key = 'Gestures';
            else {
                // Try adding "s" or "es"
                const pluralS = manifestKeys.find(k => k.toLowerCase() === lower + 's');
                if (pluralS) {
                    key = pluralS;
                } else {
                    const pluralES = manifestKeys.find(k => k.toLowerCase() === lower + 'es');
                    if (pluralES) {
                        key = pluralES;
                    }
                }
            }
        }

        if (!this.manifest[key]) {
            console.warn(`[Avatar] Category not found: ${category} (mapped to ${key})`);
            return null;
        }
        const anims = this.manifest[key];
        const randomAnim = anims[Math.floor(Math.random() * anims.length)];
        return this.playAnimation(randomAnim.url, loop, fadeTime, newState);
    }

    public async playAnimation(url: string, loop: boolean = false, fadeTime: number = 0.5, newState: AnimState = 'gesture') {
        const result = await this.playAnimationInternal(url, loop, fadeTime, newState);
        if (!result && this.canTransitionTo('idle')) {
            console.warn(`[Avatar] No clip produced for ${url}. Restoring standard idle fallback.`);
            await this.restoreModelIdle(fadeTime);
        }
        return result;
    }

    private async playAnimationInternal(url: string, loop: boolean = false, fadeTime: number = 0.5, newState: AnimState = 'gesture'): Promise<THREE.AnimationAction | null> {
        if (!this.vrm || !this.mixer) return null;
        if (!this.transitionToState(newState)) {
            console.log(`[Avatar] Ignored animation request for ${url} (lower priority). Current state: ${this.animState}`);
            return null;
        }
        try {
            let clip: THREE.AnimationClip | null = null;
            const lowerUrl = url.toLowerCase();

            if (lowerUrl.endsWith('.fbx')) {
                clip = await loadMixamoAnimation(url, this.vrm);
            } else if (lowerUrl.endsWith('.bvh')) {
                clip = await loadBVHAnimation(url, this.vrm);
            } else if (lowerUrl.endsWith('.vrma')) {
                try {
                    const loader = new GLTFLoader();
                    loader.register((parser) => new VRMAnimationLoaderPlugin(parser));
                    const gltf = await loader.loadAsync(url);
                    // VRMA v3 stores animations in vrmAnimations (plural), v2 uses vrmAnimation (singular)
                    const vrmAnimations = gltf.userData.vrmAnimations || (gltf.userData.vrmAnimation ? [gltf.userData.vrmAnimation] : null);
                    if (vrmAnimations && vrmAnimations.length > 0) {
                        clip = createVRMAnimationClip(vrmAnimations[0], this.vrm as any);
                        if (clip) {
                            console.log(`[Avatar] VRMA loaded successfully: ${url.split('/').pop()}`);
                        } else {
                            console.warn(`[Avatar] VRMA clip creation returned null: ${url}`);
                        }
                    } else if (gltf.animations && gltf.animations.length > 0) {
                        // Fallback: use raw GLTF animation if VRMA plugin couldn't parse it
                        clip = gltf.animations[0];
                        console.log(`[Avatar] VRMA fallback to raw animation: ${url.split('/').pop()}`);
                    } else {
                        console.warn(`[Avatar] VRMA loaded but no animation data found: ${url}`, Object.keys(gltf.userData));
                    }
                } catch (vrmaErr) {
                    console.warn(`[Avatar] VRMA load failed for ${url}:`, vrmaErr);
                }
            }

            if (clip) {
                const newAction = this.mixer.clipAction(clip);
                newAction.reset().setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
                newAction.clampWhenFinished = !loop;

                if (this.currentAction) this.currentAction.fadeOut(fadeTime);
                newAction.fadeIn(fadeTime).play();

                this.currentAction = newAction;
                this.animState = newState;
                this.isProceduralIdle = false; // Reset procedural idle flag on successful animation play
                this.tposeWarningSystem.setCurrentAction(newAction);
                return newAction;
            }
            return null;
        } catch (err) {
            console.error(`[Avatar] Play failed for ${url}:`, err);
            return null;
        }
    }

    public setZoom(enabled: boolean) { this.isZoomed = enabled; }

    /**
     * M7: Trigger a quick procedural micro-gesture.
     * Types: "nod", "shake", "tilt", "look_away", "double_take"
     */
    /**
     * Apply BlendShape expressions triggered by the soundboard.
     * Maps soundboard tag names (e.g. "surprised", "happy") to VRM expression names,
     * applies them with the given weight, and fades them out after the duration.
     */
    private applySoundboardBlendShapes(blendShapes: Record<string, number>, duration: number) {
        if (!this.vrm?.expressionManager) return;

        // Map soundboard descriptive names to VRM expression preset names
        const nameMap: Record<string, string> = {
            'surprised': 'surprised',
            'happy': 'happy',
            'angry': 'angry',
            'sad': 'sad',
            'relaxed': 'relaxed',
            'neutral': 'neutral',
            // Mouth shapes
            'mouthSmile': 'happy',
            'mouthOpen': 'aa',
            // Eye shapes
            'eyeWide': 'surprised',
            'eyeSquint': 'relaxed',
            'eyeClose': 'relaxed',
            // Head/body
            'nod': 'happy',
            'thinking': 'neutral',
        };

        const appliedExpressions: { name: string; weight: number }[] = [];

        for (const [key, weight] of Object.entries(blendShapes)) {
            const vrmName = nameMap[key] || key;
            try {
                this.vrm.expressionManager.setValue(vrmName, weight);
                appliedExpressions.push({ name: vrmName, weight });
            } catch (err) {
                // Expression name not found in VRM — skip silently
                console.warn(`[Avatar] BlendShape "${vrmName}" not found in VRM expressions`);
            }
        }

        if (appliedExpressions.length > 0) {
            this.log(`[Avatar] Soundboard BlendShape: ${appliedExpressions.map(e => `${e.name}=${e.weight}`).join(', ')}`, 'var(--neon-blue)');
        }

        // Fade out after duration
        setTimeout(() => {
            if (!this.vrm?.expressionManager) return;
            for (const { name } of appliedExpressions) {
                try {
                    this.vrm.expressionManager.setValue(name, 0);
                } catch { }
            }
        }, duration);
    }

    public triggerMicroGesture(type: string) {
        const durations: Record<string, number> = {
            'nod': 0.4, 'shake': 0.5, 'tilt': 0.35,
            'look_away': 0.6, 'double_take': 0.5,
        };
        this.microGestureQueue.push({ type, duration: durations[type] || 0.4 });
        this.log(`[Avatar] Micro-gesture queued: ${type}`, 'var(--neon-blue)');
    }

    /**
     * M7: Set emotional body language state.
     * States: "neutral", "happy", "sad", "curious", "concerned", "excited", "calm"
     */
    public setEmotionalState(state: string) {
        const valid = ['neutral', 'happy', 'sad', 'curious', 'concerned', 'excited', 'calm'];
        this.emotionalState = valid.includes(state) ? state : 'neutral';
        this.emotionalInfluence = 0;
        this.log(`[Avatar] Emotional state: ${this.emotionalState}`, 'var(--neon-blue)');
        // Morph the Harmonic Heartbeat to match
        ambientSoundEngine.setEmotionalChord(this.emotionalState);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // AUTONOMOUS CONSCIOUSNESS KERNEL
    // Jen is NEVER "off" — she always has drives, awareness, and agency.
    // This is NOT a toggle. This IS Jen.
    // LLM → <emotion:happy> → applyEmotionAnimation → playCategory("Happy")
    // Drives → urgency ranking → free-will decision → body action
    // ═══════════════════════════════════════════════════════════════════════

    // Autonomous variables moved to MovementEngine.ts

    /**
     * Map emotion → animation category + face expression.
     * LLM → <emotion:happy> → applyEmotionAnimation → playCategory("Happy")
     * This is reactive self-puppeteering: Jen's AI output drives her body.
     */
    public applyEmotionAnimation(emotion: string, intensity: number = 1.0) {
        if (!this.vrm) return;
        const emotionToCategory: Record<string, string> = {
            'happy': 'Happy', 'excited': 'Happy', 'sad': 'Sad', 'concerned': 'Sad',
            'angry': 'Angry', 'surprised': 'Surprised', 'curious': 'Thinking',
            'thinking': 'Thinking', 'neutral': 'Idle', 'relaxed': 'Idle',
            'calm': 'Idle', 'playful': 'Dance', 'grateful': 'Happy',
        };
        const category = emotionToCategory[emotion.toLowerCase()] || 'Idle';
        this.setEmotionalState(emotion.toLowerCase());

        // Idle expressions can automatically restore the model's resting idle pose.
        // Other emotive expressions change facial blendshapes but DO NOT play full-body animations automatically.
        if (category === 'Idle') {
            this.restoreModelIdle(0.5);
        }
        if (this.vrm.expressionManager) {
            const exprMap: Record<string, string> = {
                'happy': 'happy', 'sad': 'sad', 'angry': 'angry',
                'surprised': 'surprised', 'relaxed': 'relaxed', 'neutral': 'neutral',
            };
            const expr = exprMap[emotion.toLowerCase()];
            if (expr) {
                this.vrm.expressionManager.setValue(expr, intensity);
                setTimeout(() => { this.vrm?.expressionManager?.setValue(expr, 0); }, 3000);
            }
        }
        // Interaction resets awareness timers
        this.onUserInteraction();
    }

    public async playAnimationByName(name: string, loop: boolean = false, fadeTime: number = 0.5): Promise<THREE.AnimationAction | null> {
        if (!this.vrm) return null;

        const lowerName = name.toLowerCase().trim();

        // 1. If 'name' is directly a URL (ends with .fbx, .bvh, .vrma), play it directly
        if (lowerName.endsWith('.fbx') || lowerName.endsWith('.bvh') || lowerName.endsWith('.vrma')) {
            this.log(`🎬 Playing animation by URL: ${name}`, 'var(--neon-blue)');
            return this.playAnimation(name, loop, fadeTime, 'override');
        }

        // 2. Otherwise search for 'name' in the animation manifest (case-insensitively)
        if (!this.manifest) {
            console.warn('[Avatar] Cannot play animation by name - manifest not loaded');
            return null;
        }

        let foundUrl: string | null = null;
        for (const category of Object.values(this.manifest)) {
            if (Array.isArray(category)) {
                const match = category.find((anim: any) => anim.name && anim.name.toLowerCase() === lowerName);
                if (match && match.url) {
                    foundUrl = match.url;
                    break;
                }
            }
        }

        if (foundUrl) {
            this.log(`🎬 Playing animation: ${name} (${foundUrl})`, 'var(--neon-blue)');
            return this.playAnimation(foundUrl, loop, fadeTime, 'override');
        } else {
            console.warn(`[Avatar] Animation name not found in manifest: ${name}`);
            this.log(`⚠️ Animation not found in manifest: ${name}`, 'var(--neon-yellow)');
            return null;
        }
    }

    /** User interaction satisfies social need and resets aloneness timer. */
    public onUserInteraction() {
        this.movementEngine.onUserInteraction();
    }

    /**
     * ── CODE AGENCY EXECUTOR ──
     * Routes <code:...> bracket tokens to CodeAgency methods.
     * Supported actions: search, read, write, edit, exec, git_status, list_dir
     */
    private async executeCodeAction(action: string, params: Record<string, string>, fullMatch: string) {
        this.log(`💻 <code:${action}> → CodeAgency`, 'var(--neon-blue)');
        try {
            switch (action) {
                case 'search': {
                    const query = params['q'] || params['query'] || '';
                    const glob = params['glob'] || '*';
                    if (!query) {
                        this.log('⚠️ <code:search> requires q= or query= parameter', 'var(--neon-yellow)');
                        return;
                    }
                    const results = await this.codeAgency.searchCode(query, glob);
                    this.log(`🔍 Code search "${query}": ${results.length} results`, 'var(--neon-green)');
                    // Dispatch results back so the LLM can see them
                    window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                        detail: { action: 'search', query, results, success: true }
                    }));
                    break;
                }
                case 'read': {
                    const path = params['path'] || params['file'] || '';
                    if (!path) {
                        this.log('⚠️ <code:read> requires path= parameter', 'var(--neon-yellow)');
                        return;
                    }
                    const maxLines = parseInt(params['maxLines'] || params['lines'] || '200', 10);
                    const content = await this.codeAgency.readFile(path, maxLines);
                    if (content !== null) {
                        this.log(`📖 Read ${path} (${content.split('\n').length} lines)`, 'var(--neon-green)');
                        window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                            detail: { action: 'read', path, content, success: true }
                        }));
                    } else {
                        this.log(`⚠️ Failed to read ${path}`, 'var(--neon-yellow)');
                        window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                            detail: { action: 'read', path, success: false, message: 'File not found or access denied' }
                        }));
                    }
                    break;
                }
                case 'exec': {
                    const cmd = params['cmd'] || params['command'] || '';
                    if (!cmd) {
                        this.log('⚠️ <code:exec> requires cmd= or command= parameter', 'var(--neon-yellow)');
                        return;
                    }
                    const approve = params['approve'] !== 'false';
                    const result = await this.codeAgency.exec(cmd, approve);
                    this.log(`⚡ Exec: ${result.success ? 'OK' : 'FAIL'} — ${result.message}`, result.success ? 'var(--neon-green)' : 'var(--neon-yellow)');
                    window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                        detail: { action: 'exec', command: cmd, ...result }
                    }));
                    break;
                }
                case 'write': {
                    const path = params['path'] || params['file'] || '';
                    const content = params['content'] || '';
                    if (!path) {
                        this.log('⚠️ <code:write> requires path= parameter', 'var(--neon-yellow)');
                        return;
                    }
                    const result = await this.codeAgency.writeFile(path, content);
                    this.log(`📝 Write ${path}: ${result.success ? 'OK' : 'FAIL'}`, result.success ? 'var(--neon-green)' : 'var(--neon-yellow)');
                    window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                        detail: { action: 'write', path, ...result }
                    }));
                    break;
                }
                case 'edit': {
                    const path = params['path'] || params['file'] || '';
                    if (!path) {
                        this.log('⚠️ <code:edit> requires path= parameter', 'var(--neon-yellow)');
                        return;
                    }
                    // Parse search/replace blocks from params — fallback to fullMatch extraction
                    this.log(`✏️ Edit ${path} — requires structured blocks`, 'var(--neon-blue)');
                    window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                        detail: { action: 'edit', path, success: false, message: 'Edit blocks must be provided via structured params' }
                    }));
                    break;
                }
                case 'git_status':
                case 'git': {
                    const status = await this.codeAgency.gitStatus();
                    this.log(`📊 Git status: ${status}`, 'var(--neon-green)');
                    window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                        detail: { action: 'git_status', status, success: true }
                    }));
                    break;
                }
                case 'list_dir':
                case 'ls': {
                    const dir = params['dir'] || params['path'] || '.';
                    const files = await this.codeAgency.listDir(dir);
                    this.log(`📁 ${dir}: ${files.length} entries`, 'var(--neon-green)');
                    window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                        detail: { action: 'list_dir', dir, files, success: true }
                    }));
                    break;
                }
                default:
                    this.log(`⚠️ Unknown code action: ${action}`, 'var(--neon-yellow)');
            }
        } catch (err: any) {
            this.log(`💥 Code action "${action}" failed: ${err.message}`, 'var(--neon-red)');
            window.dispatchEvent(new CustomEvent('foveai_code_action_result', {
                detail: { action, success: false, message: err.message }
            }));
        }
    }

    private dispatchActionFeedback(message: string) {
        window.dispatchEvent(new CustomEvent('foveai_action_result', { detail: { message } }));
    }

    /**
     * ── SOCIAL MODE CONTROLLER ──
     * Called when BracketParser detects <mode:coexist>, <mode:cowork>, etc.
     * Adjusts personality parameters, drive baselines, and movement policy
     * to match the relationship-appropriate behavioral context.
     */
    public setSocialMode(mode: string) {
        const validModes = ['coexist', 'cowork', 'coop', 'rest', 'follow', 'intimate'];
        if (!validModes.includes(mode)) {
            this.log(`⚠️ Unknown social mode: ${mode}`, 'var(--neon-yellow)');
            return;
        }
        this.log(`🎭 Social Mode: ${mode}`, 'var(--neon-blue)');
        this.movementEngine.setSocialMode(mode);

        switch (mode) {
            case 'coexist':
                this.curiosityStrength = 0.5;
                break;
            case 'cowork':
                this.curiosityStrength = 0.7;
                break;
            case 'coop':
                this.curiosityStrength = 0.8;
                break;
            case 'follow':
                this.log(`🚶 Follow mode active — maintaining ~1.5m distance`, 'var(--neon-green)');
                break;
            case 'intimate':
                this.curiosityStrength = 1.0;
                break;
        }
    }

    /**
     * ── LLM-SPATIAL COMMAND EXECUTOR ──
     * Routes movement commands from the LLM (via BracketParser → foveai_movement_command)
     * to both the AvatarManager's movement system AND the MovementEngine.
     * This is Jen's intentional movement channel: she decides to move, her body follows.
     */
    private executeMovementCommand(command: string, params: any) {
        if (!this.vrm) {
            this.log(`⚠️ Cannot execute "${command}" — VRM not loaded`, 'var(--neon-yellow)');
            return;
        }
        
        // If we are in override or express state, and receive an intentional movement command, break out of it
        if ((this.animState === 'override' || this.animState === 'express') && (command === 'walk_forward' || command === 'move_to')) {
            this.log(`🚶 Breaking out of ${this.animState} state to execute movement command: ${command}`, 'var(--neon-blue)');
            this.isCrouching = false;
            this.animState = 'idle'; // Reset state so transition to walk succeeds
        }

        switch (command) {
            case 'walk_forward': {
                const meters = parseFloat(params?.meters || params?.distance || '1');
                // Compute the target position using the VRM's facing direction,
                // then pass it to both AvatarManager and the MovementEngine.
                if (this.vrm) {
                    const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(this.vrm.scene.quaternion);
                    const target = this.originalPos.clone().add(forward.multiplyScalar(meters));
                    this.moveTarget = target;
                    this.steeringActive = false;
                    this.movementEngine.commandWalkForward(target);
                }
                this.log(`🚶 LLM Directed: Walk forward ${meters}m`, 'var(--neon-blue)');
                break;
            }
            case 'move_to': {
                let target: THREE.Vector3;
                if (params?.x !== undefined && params?.y !== undefined && params?.z !== undefined) {
                    target = new THREE.Vector3(
                        parseFloat(params.x), parseFloat(params.y), parseFloat(params.z)
                    );
                } else if (params?.target && Array.isArray(params.target)) {
                    target = new THREE.Vector3(params.target[0], params.target[1], params.target[2]);
                } else {
                    this.log(`⚠️ move_to requires x,y,z or target array`, 'var(--neon-yellow)');
                    return;
                }
                this.setDestination(target);
                this.movementEngine.commandMoveTo(target);
                this.log(`🎯 LLM Directed: Move to (${target.x.toFixed(1)}, ${target.y.toFixed(1)}, ${target.z.toFixed(1)})`, 'var(--neon-blue)');
                break;
            }
            case 'steer': {
                const enabled = params?.enabled === 'true' || params?.enabled === true || command.endsWith('on');
                this.steeringActive = enabled;
                this.movementEngine.setSteeringActive(enabled);
                this.log(enabled ? `🕹️ Steering mode ON — user guides body` : `🕹️ Steering mode OFF — autonomous`, 'var(--neon-blue)');
                break;
            }
            case 'stop':
            case 'move_stop': {
                this.moveTarget = null;
                this.steeringActive = false;
                this.velocity.set(0, 0, 0);
                this.movementEngine.setSteeringActive(false);
                this.log(`✋ Movement stopped — holding position`, 'var(--neon-yellow)');
                break;
            }
            case 'interact': {
                const targetType = params?.target || params?.object || '';
                const actionType = params?.action || params?.type || 'view';
                this.interactWithObject(targetType, actionType);
                break;
            }
            default:
                this.log(`⚠️ Unknown movement command: ${command}`, 'var(--neon-yellow)');
        }
    }

    private activeInteractionInterval: any = null;

    private async interactWithObject(targetType: string, actionType: string) {
        if (!this.vrm) return;
        if (this.activeInteractionInterval) {
            clearInterval(this.activeInteractionInterval);
            this.activeInteractionInterval = null;
        }

        const lowerTarget = targetType.toLowerCase().trim();
        const lowerAction = actionType.toLowerCase().trim();
        this.log(`🎯 Intentional Interaction: Target="${lowerTarget}", Action="${lowerAction}"`, 'var(--neon-green)');

        // 1. Locate the object in the SpatialEnvironment
        const spatialEnv = (window as any).spatialEnvironment;
        if (!spatialEnv) {
            this.log(`⚠️ No SpatialEnvironment available to locate "${lowerTarget}"`, 'var(--neon-yellow)');
            this.dispatchActionFeedback(`Failed: No spatial mapping available to locate "${targetType}".`);
            return;
        }

        const room = spatialEnv.rooms.get(spatialEnv.currentRoom);
        if (!room || !room.meshes) {
            this.log(`⚠️ SpatialEnvironment has no mesh data in the current room`, 'var(--neon-yellow)');
            this.dispatchActionFeedback(`Failed: Cannot interact with "${targetType}", no mapped meshes found in current room.`);
            return;
        }

        // Find best matching mesh by type or label
        let bestMesh = null;
        for (const mesh of room.meshes) {
            const typeMatch = mesh.type.toLowerCase() === lowerTarget;
            const labelMatch = mesh.label && mesh.label.toLowerCase().includes(lowerTarget);
            if (typeMatch || labelMatch) {
                bestMesh = mesh;
                break;
            }
        }

        // Fallbacks if no exact match (e.g. if looking for "bed" and we only have "furniture" type)
        if (!bestMesh) {
            if (lowerTarget === 'floor' || lowerTarget === 'ground') {
                bestMesh = room.meshes.find((m: any) => m.type === 'floor');
            } else {
                bestMesh = room.meshes.find((m: any) => m.type === 'furniture');
            }
        }

        if (!bestMesh) {
            this.log(`⚠️ Could not find any spatial feature matching "${lowerTarget}"`, 'var(--neon-yellow)');
            this.dispatchActionFeedback(`Failed: Object "${targetType}" not found in current room mapping.`);
            return;
        }

        const center = bestMesh.geometry.center;
        const size = bestMesh.geometry.size;
        const targetPos = new THREE.Vector3(center.x, center.y, center.z);

        let landingPos = targetPos.clone();
        if (bestMesh.type === 'floor') {
            // just walk to the floor coordinate
        } else if (lowerAction === 'view' || lowerAction === 'examine' || lowerAction === 'look') {
            // stand 1.0 meter away, facing it
            const dirToAvatar = new THREE.Vector3().subVectors(this.originalPos, targetPos);
            dirToAvatar.y = 0;
            dirToAvatar.normalize();
            landingPos.addScaledVector(dirToAvatar, 1.0);
        } else if (lowerAction === 'sit' || lowerAction === 'lay_down' || lowerAction === 'kneel') {
            // Move exactly to object center, but adjust y based on object top
            landingPos.y = center.y + size.y / 2;
        }

        // 2. Set the destination to the object/interaction spot
        this.log(`🚶 Walking to "${lowerTarget}" at (${landingPos.x.toFixed(1)}, ${landingPos.y.toFixed(1)}, ${landingPos.z.toFixed(1)})...`, 'var(--neon-blue)');
        this.setDestination(landingPos);
        this.movementEngine.commandMoveTo(landingPos);

        // Wait until we arrive (check distance)
        this.activeInteractionInterval = setInterval(() => {
            if (!this.vrm) {
                clearInterval(this.activeInteractionInterval);
                this.activeInteractionInterval = null;
                return;
            }
            const dist = this.originalPos.distanceTo(landingPos);
            if (dist < 0.45 || !this.isWalking) { // arrived or stopped
                clearInterval(this.activeInteractionInterval);
                this.activeInteractionInterval = null;
                this.log(`✨ Arrived at "${lowerTarget}"! Triggering action "${lowerAction}"`, 'var(--neon-green)');
                this.performAnimationAction(lowerTarget, lowerAction, bestMesh);
            }
        }, 500);
    }

    private async performAnimationAction(target: string, action: string, mesh: any) {
        if (!this.vrm) return;

        // Face the target (or if we sit, turn around or face forward)
        if (mesh && mesh.planeNormal) {
            const angle = Math.atan2(mesh.planeNormal.x, mesh.planeNormal.z);
            this.vrm.scene.rotation.y = angle;
        } else {
            // face user camera
            const cam = (window as any).env?.camera;
            if (cam) {
                const headWorldPos = new THREE.Vector3();
                this.vrm.scene.getWorldPosition(headWorldPos);
                const toCamera = new THREE.Vector3().subVectors(cam.position, headWorldPos);
                toCamera.y = 0;
                if (toCamera.lengthSq() > 0.04) {
                    const angle = Math.atan2(-toCamera.x, -toCamera.z);
                    this.vrm.scene.rotation.y = angle;
                }
            }
        }

        switch (action) {
            case 'sit': {
                this.log(`🪑 Sitting on "${target}"`, 'var(--neon-blue)');
                const anim = await this.playAnimationByName('sit', true, 0.5) ||
                    await this.playAnimationByName('Sit', true, 0.5) ||
                    await this.playAnimationByName('Sitting', true, 0.5);
                if (!anim) {
                    this.isCrouching = true;
                    this.applyProceduralIdle();
                    await this.playAnimationByName('Idle', true, 0.5);
                    this.dispatchActionFeedback(`Action "sit" on "${target}" succeeded but used procedural fallback because specific "sit" animation clip was missing.`);
                } else {
                    this.dispatchActionFeedback(`Action "sit" on "${target}" succeeded.`);
                }
                break;
            }
            case 'lay_down':
            case 'lie_down': {
                this.log(`🛌 Laying down on "${target}"`, 'var(--neon-blue)');
                const anim = await this.playAnimationByName('lay_down', true, 0.5) ||
                    await this.playAnimationByName('lie_down', true, 0.5) ||
                    await this.playAnimationByName('Lying', true, 0.5);
                if (!anim) {
                    this.isCrouching = true;
                    this.applyProceduralIdle();
                    await this.playAnimationByName('Idle', true, 0.5);
                    this.dispatchActionFeedback(`Action "lay_down" on "${target}" succeeded but used procedural fallback because specific "lay_down" animation clip was missing.`);
                } else {
                    this.dispatchActionFeedback(`Action "lay_down" on "${target}" succeeded.`);
                }
                break;
            }
            case 'jump': {
                this.log(`🦘 Jumping on "${target}"`, 'var(--neon-blue)');
                const anim = await this.playAnimationByName('jump', false, 0.2) ||
                    await this.playAnimationByName('Jump', false, 0.2);
                if (!anim) {
                    await this.playAnimationByName('Idle', true, 0.5);
                    this.dispatchActionFeedback(`Action "jump" on "${target}" failed due to missing animation.`);
                } else {
                    this.dispatchActionFeedback(`Action "jump" on "${target}" succeeded.`);
                }
                break;
            }
            case 'stand':
            case 'stand_on': {
                this.log(`🧍 Standing on "${target}"`, 'var(--neon-blue)');
                this.isCrouching = false;
                await this.playAnimationByName('stand', false, 0.5) ||
                    await this.playAnimationByName('Idle', true, 0.5);
                this.dispatchActionFeedback(`Action "stand" on "${target}" succeeded.`);
                break;
            }
            case 'lift':
            case 'lift_up': {
                this.log(`💪 Lifting up "${target}"`, 'var(--neon-blue)');
                const anim = await this.playAnimationByName('lift', false, 0.5) ||
                    await this.playAnimationByName('pick_up', false, 0.5);
                if (!anim) {
                    await this.playAnimationByName('Idle', true, 0.5);
                    this.dispatchActionFeedback(`Action "lift" on "${target}" failed due to missing animation.`);
                } else {
                    this.dispatchActionFeedback(`Action "lift" on "${target}" succeeded.`);
                }
                break;
            }
            case 'view':
            case 'examine':
            case 'look': {
                this.log(`👀 Examining "${target}"`, 'var(--neon-blue)');
                if (mesh && mesh.geometry) {
                    const targetPos = new THREE.Vector3(mesh.geometry.center.x, mesh.geometry.center.y, mesh.geometry.center.z);
                    this.setGazeTarget(targetPos);
                }
                await this.playAnimationByName('look_around', false, 0.5) ||
                    await this.playAnimationByName('thinking', false, 0.5);
                setTimeout(() => {
                    this.clearGazeTarget();
                }, 4000);
                this.dispatchActionFeedback(`Action "${action}" on "${target}" succeeded.`);
                break;
            }
            default: {
                const anim = await this.playAnimationByName(action, false, 0.5);
                if (!anim) {
                    this.log(`⚠️ Unrecognized interaction action: "${action}"`, 'var(--neon-yellow)');
                    this.dispatchActionFeedback(`Action "${action}" on "${target}" failed: unknown action or missing animation.`);
                } else {
                    this.dispatchActionFeedback(`Action "${action}" on "${target}" succeeded.`);
                }
                break;
            }
        }
    }

    /**
     * CONSCIOUSNESS KERNEL — Jen's autonomous decision loop.
     * Always running. Every ~3.5s: evaluate drives → rank urgencies → act.
     * This is free will: Jen decides for herself based on her internal state.
     */
    /** Consciousness status for HUD / diagnostics */
    public getConsciousnessStatus() {
        const status = this.movementEngine.getStatus();
        return {
            drives: status.drives,
            awareness: status.awareness as any,
            state: status.state,
            emotion: status.emotionalState,
        };
    }

    /**
     * M7: Navigate to a world-space coordinate (called by LocalBrain [MOVE_TO]).
     */
    public setDestination(target: THREE.Vector3) {
        if (!this.vrm) return;
        this.moveTarget = target.clone();
        this.steeringActive = false;
        this.movementEngine.setDestination(target);
        this.log(`[Avatar] Destination set: (${target.x.toFixed(1)}, ${target.y.toFixed(1)}, ${target.z.toFixed(1)})`, 'var(--neon-blue)');
    }

    /**
     * M7: Process micro-gesture queue and timers.
     */
    private updateMicroGestures(delta: number) {
        if (this.activeMicroGesture) {
            this.microGestureTimer -= delta;
            if (this.microGestureTimer <= 0) {
                this.activeMicroGesture = null;
            }
        }
        if (!this.activeMicroGesture && this.microGestureQueue.length > 0) {
            const gesture = this.microGestureQueue.shift()!;
            this.activeMicroGesture = gesture.type;
            this.microGestureTimer = gesture.duration;
        }
    }

    /**
     * Procedural idle fallback: creates a gentle breathing/swaying motion
     * when no animation clip is available. This prevents the avatar from
     * freezing in T-Pose when animations fail to load.
     */
    private proceduralIdleTime: number = 0;
    private isProceduralIdle: boolean = false;

    private applyProceduralIdle() {
        this.isProceduralIdle = true;
        this.proceduralIdleTime = 0;
        console.log('[Avatar] Switched to procedural idle mode.');
    }

    /**
     * Update procedural idle animations (breathing, gentle sway, micro-movements).
     * Called when no animation clip is active to keep the avatar feeling alive.
     */
    private updateProceduralIdle(delta: number, camera?: THREE.Camera) {
        if (!this.vrm) return;
        this.proceduralIdleTime += delta;

        const t = this.proceduralIdleTime;

        // --- M7: Emotional state modifiers ---
        const emotionMods: Record<string, { breathRate: number; armDrop: number; spineCurve: number; headForward: number }> = {
            'happy': { breathRate: 1.4, armDrop: 0.05, spineCurve: -0.02, headForward: 0.03 },
            'sad': { breathRate: 0.8, armDrop: 0.15, spineCurve: 0.06, headForward: 0.08 },
            'curious': { breathRate: 1.1, armDrop: 0.0, spineCurve: -0.01, headForward: 0.12 },
            'concerned': { breathRate: 0.9, armDrop: 0.08, spineCurve: 0.03, headForward: 0.06 },
            'excited': { breathRate: 1.6, armDrop: -0.05, spineCurve: -0.03, headForward: 0.05 },
            'calm': { breathRate: 0.7, armDrop: 0.02, spineCurve: 0.0, headForward: 0.0 },
            'neutral': { breathRate: 1.0, armDrop: 0.0, spineCurve: 0.0, headForward: 0.0 },
        };
        const emo = emotionMods[this.emotionalState] || emotionMods['neutral'];
        const emoBreath = Math.sin(t * emo.breathRate) * 0.5 + 0.5;

        // --- M7: Micro-gesture influence ---
        let microInfluence = { x: 0, y: 0, z: 0 };
        if (this.activeMicroGesture) {
            const totalDuration = this.activeMicroGesture === 'nod' ? 0.4 :
                this.activeMicroGesture === 'shake' ? 0.5 :
                    this.activeMicroGesture === 'tilt' ? 0.35 :
                        this.activeMicroGesture === 'look_away' ? 0.6 : 0.5;
            const progress = 1 - (this.microGestureTimer / totalDuration);
            const wave = Math.sin(progress * Math.PI);
            switch (this.activeMicroGesture) {
                case 'nod': microInfluence.x = -wave * 0.15; break;
                case 'shake': microInfluence.y = wave * 0.12; break;
                case 'tilt': microInfluence.z = wave * 0.1; break;
                case 'look_away': microInfluence.y = wave * 0.2; break;
                case 'double_take': microInfluence.x = -wave * 0.1; microInfluence.y = wave * 0.15; break;
            }
        }

        // --- M7: Curiosity head tracking toward camera (Local Space Transform) ---
        let curiosityInfluence = { x: 0, y: 0 };
        if (this.curiosityStrength > 0 && camera) {
            const headWorldPos = new THREE.Vector3();
            this.vrm.scene.getWorldPosition(headWorldPos);
            const toCamera = new THREE.Vector3().subVectors(camera.position, headWorldPos).normalize();
            // Transform direction to local space of the avatar to handle body rotations correctly
            const localToCamera = toCamera.clone().applyQuaternion(this.vrm.scene.quaternion.clone().invert());
            const angleY = Math.atan2(-localToCamera.x, -localToCamera.z);
            const angleX = -Math.atan2(localToCamera.y, Math.sqrt(localToCamera.x * localToCamera.x + localToCamera.z * localToCamera.z));

            // Clamp angles to natural human head movement limits
            const limitY = Math.PI / 4; // 45 deg
            const limitX = Math.PI / 6; // 30 deg
            curiosityInfluence.y = THREE.MathUtils.clamp(angleY, -limitY, limitY) * this.curiosityStrength;
            curiosityInfluence.x = THREE.MathUtils.clamp(angleX, -limitX, limitX) * this.curiosityStrength;
        }

        const sway = Math.sin(t * 0.3) * 0.02;

        // Spine: sway + emotional curve
        const spine = this.bones['spine'];
        if (spine) {
            spine.rotation.z = sway;
            spine.rotation.x = emoBreath * 0.03 + emo.spineCurve;
        }

        // Chest: emotional-rate breathing
        const chest = this.bones['chest'];
        if (chest) {
            chest.rotation.x = emoBreath * 0.06;
        }

        // Arms: emotional drop + breathing
        const lArm = this.bones['leftUpperArm'];
        const rArm = this.bones['rightUpperArm'];
        if (lArm) lArm.rotation.z = 1.35 + (emoBreath * 0.08) + emo.armDrop;
        if (rArm) rArm.rotation.z = -1.35 - (emoBreath * 0.08) - emo.armDrop;

        // Head: micro-gesture + curiosity + emotion + breathing
        // Reduced oscillation amplitudes to prevent eye twitch
        const head = this.bones['head'];
        if (head) {
            const baseY = Math.sin(t * 0.5) * 0.03 + Math.sin(t * 0.3) * 0.04;
            const baseX = Math.cos(t * 0.3) * 0.02;
            head.rotation.y = baseY + microInfluence.y + curiosityInfluence.y;
            head.rotation.x = baseX + emo.headForward + microInfluence.x + curiosityInfluence.x;
            head.rotation.z = microInfluence.z;
            if (this.isZoomed) {
                head.rotation.x += 0.15 * this.zoomLerp;
            }
        }

        // Hips: subtle weight shift
        const hips = this.bones['hips'];
        if (hips) {
            hips.position.y = 0.85 + Math.sin(t * 0.8) * 0.005;
        }
    }

    public async walkForward(meters: number) {
        if (!this.vrm) return;
        this.log(`Initiating Autonomous Walk: ${meters}m`, 'var(--neon-blue)');

        // Calculate target 
        const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(this.vrm.scene.quaternion);
        const target = this.originalPos.clone().add(forward.multiplyScalar(meters));

        this.moveTarget = target;
        this.steeringActive = false;
    }

    public setManualVelocity(vel: THREE.Vector3) {
        this.velocity.copy(vel);
    }

    public update(delta: number, camera: THREE.Camera) {
        if (this.vrm) {
            // Clamp delta to max 16ms (~60fps tick) to prevent physics velocity spikes/fluttering
            const safeDelta = Math.min(Math.max(delta, 0.001), 0.016);
            const t = performance.now() * 0.001;
            this.uTime.value = t;

            if (this.mixer) this.mixer.update(safeDelta);
            this.vrm.update(safeDelta);

            // --- DYNAMIC POSITION REFERENCE UPDATE (XR & Crouch aware) ---
            const isXR = !!(window as any).xrSession;
            let baseHeight = isXR ? 0.0 : -0.8;
            let zoomHeight = isXR ? 0.0 : -0.65;

            // Update grounding dynamically based on SpatialEnvironment floor center height
            if (isXR && (window as any).spatialEnvironment) {
                const navData = (window as any).spatialEnvironment.getNavigationData();
                if (navData && navData.floorCenter) {
                    baseHeight = navData.floorCenter.y;
                    zoomHeight = navData.floorCenter.y + 0.15;
                }
            }

            const currentBaseY = this.isCrouching ? baseHeight - 0.3 : baseHeight;
            const currentZoomY = this.isCrouching ? zoomHeight - 0.3 : zoomHeight;

            this.originalPos.y = currentBaseY;

            // Calculate zoom position dynamically based on originalPos
            this.zoomPos.copy(this.originalPos);
            this.zoomPos.y = currentZoomY;
            this.zoomPos.z = this.originalPos.z + 1.45;

            // --- ZOOM LERP ---
            const zoomTarget = this.isZoomed ? 1.0 : 0.0;
            this.zoomLerp = THREE.MathUtils.lerp(this.zoomLerp, zoomTarget, delta * 2.0);
            this.vrm.scene.position.lerpVectors(this.originalPos, this.zoomPos, this.zoomLerp);

            // --- MOVEMENT LOGIC (OMEGA_076) ---
            const engineUpdate = this.movementEngine.update(delta, this.originalPos, camera ? camera.position : undefined);

            let currentVelocity = this.velocity.clone();
            if (!this.steeringActive) {
                currentVelocity.copy(engineUpdate.velocity);
                this.moveTarget = this.movementEngine.getMoveTarget();

                // If currently performing an override or express animation, clamp velocity to 0 to prevent sliding
                if (this.animState === 'override' || this.animState === 'express') {
                    currentVelocity.set(0, 0, 0);
                    this.moveTarget = null;
                }

                // Collision avoidance against detected Quest scene obstacles
                if (currentVelocity.lengthSq() > 0.001 && (window as any).spatialEnvironment) {
                    const navData = (window as any).spatialEnvironment.getNavigationData();
                    const nextPos = this.originalPos.clone().add(currentVelocity.clone().multiplyScalar(delta));
                    for (const obs of navData.obstacles) {
                        const flatDist = new THREE.Vector2(nextPos.x - obs.x, nextPos.z - obs.z).length();
                        if (flatDist < 0.4 && Math.abs(nextPos.y - obs.y) < 1.0) {
                            currentVelocity.set(0, 0, 0);
                            if (this.moveTarget) {
                                this.movementEngine.setDestination(this.originalPos); // halt the movement engine
                            }
                            console.warn('[Avatar] Obstacle collision avoided! Halted walk to', obs);
                            break;
                        }
                    }
                }
            }

            // Apply micro-gestures and animation decisions from MovementEngine
            if (engineUpdate.microGesture) {
                this.triggerMicroGesture(engineUpdate.microGesture);
            }
            if (engineUpdate.animationCategory && !this.isWalking && engineUpdate.animationCategory !== 'Idle') {
                const isLooping = (engineUpdate.animationCategory === 'Idle' || engineUpdate.animationCategory === 'Walk');
                let targetState: AnimState = 'gesture';
                if (engineUpdate.animationCategory.toLowerCase() === 'walk') targetState = 'walk';
                else if (engineUpdate.animationCategory.toLowerCase() === 'idle') targetState = 'idle';
                this.playCategory(engineUpdate.animationCategory, isLooping, 0.5, targetState);
            }

            // --- DYNAMIC GAZE TARGETING (Face user/movement direction) ---
            // Smooth lerp-based gaze to prevent eye twitch
            if (!this.hasOverrideLookAt && camera) {
                let desiredGaze = new THREE.Vector3();
                if (currentVelocity.length() <= 0.05) {
                    desiredGaze.copy(camera.position);
                } else if (this.moveTarget) {
                    desiredGaze.copy(this.moveTarget);
                } else {
                    const lookDir = currentVelocity.clone().normalize().multiplyScalar(2.0);
                    desiredGaze.copy(this.vrm.scene.position).add(lookDir);
                    desiredGaze.y = 1.2;
                }
                // Smooth lerp toward desired gaze — prevents jitter
                this.gazeTargetPos.lerp(desiredGaze, delta * this.gazeLerpSpeed);
                this.lookAtTarget.position.copy(this.gazeTargetPos);
            }

            if (currentVelocity.length() > 0.05) {
                // Update base position logically
                const frameVel = currentVelocity.clone().multiplyScalar(delta);
                this.originalPos.add(frameVel);

                // Smooth Rotation (skip if steering active)
                if (!this.steeringActive) {
                    const angle = Math.atan2(currentVelocity.x, -currentVelocity.z);
                    const targetQuat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), angle);
                    this.vrm.scene.quaternion.slerp(targetQuat, 0.1);
                }

                // Handle Animation Toggle
                if (!this.isWalking) {
                    this.isWalking = true;
                    // If we are currently in 'gesture' or lower, allow transition to walk by resetting state to idle
                    if (this.animState === 'gesture' || this.animState === 'idle' || this.animState === 'pose') {
                        this.animState = 'idle';
                    }
                    this.playCategory('Walk', true, 0.5, 'walk').then(action => {
                        this.walkActionInstance = action;
                    });
                }
            } else {
                if (this.isWalking) {
                    this.isWalking = false;
                    // Return to procedural idle — fade out walk clip, let procedural system take over
                    if (this.currentAction) {
                        this.currentAction.fadeOut(0.5);
                        this.currentAction = null;
                    }
                    this.animState = 'idle';
                    this.applyProceduralIdle();
                }
                // Dynamic Stance: Smoothly rotate body to face user when standing still (skip if steering active)
                if (camera && this.vrm && !this.steeringActive) {
                    const headWorldPos = new THREE.Vector3();
                    this.vrm.scene.getWorldPosition(headWorldPos);
                    const toCamera = new THREE.Vector3().subVectors(camera.position, headWorldPos);
                    toCamera.y = 0; // horizontal orientation only
                    if (toCamera.lengthSq() > 0.04) { // Only rotate if user is more than 20cm away
                        toCamera.normalize();
                        const angle = Math.atan2(toCamera.x, -toCamera.z);
                        const targetQuat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), angle);
                        this.vrm.scene.quaternion.slerp(targetQuat, delta * 2.0); // smooth, frame-rate independent slerp
                    }
                }
            }

            // --- AUTHORITATIVE BLENDING (OMEGA_075) ---
            // If we're in procedural idle mode (no animation clips), run the full procedural system
            // M7: Process micro-gestures each frame
            this.updateMicroGestures(delta);

            if (this.isProceduralIdle || !this.currentAction) {
                this.updateProceduralIdle(delta, camera);
            } else {
                // Blend procedural breathing with active animation clips
                const currentWeight = this.currentAction?.getEffectiveWeight() || 0;
                const isLooping = this.currentAction?.loop === THREE.LoopRepeat;
                let breathingWeight = 1.0;
                if (currentVelocity.length() > 0.1 || (this.currentAction && !isLooping)) {
                    breathingWeight = 1.0 - currentWeight;
                }

                if (breathingWeight > 0.01) {
                    const lArm = this.bones['leftUpperArm'];
                    const rArm = this.bones['rightUpperArm'];
                    const chest = this.bones['chest'];
                    const head = this.bones['head'];

                    // M7: Use emotional breathing rate
                    const emotionMods: Record<string, number> = {
                        'happy': 1.4, 'sad': 0.8, 'curious': 1.1, 'concerned': 0.9,
                        'excited': 1.6, 'calm': 0.7, 'neutral': 1.0,
                    };
                    const breathRate = emotionMods[this.emotionalState] || 1.0;
                    const breath = Math.sin(t * breathRate) * 0.5 + 0.5;

                    if (lArm) lArm.rotation.z = THREE.MathUtils.lerp(lArm.rotation.z, 1.35 + (breath * 0.2), breathingWeight);
                    if (rArm) rArm.rotation.z = THREE.MathUtils.lerp(rArm.rotation.z, -1.35 - (breath * 0.2), breathingWeight);
                    if (chest) chest.rotation.x = THREE.MathUtils.lerp(chest.rotation.x, breath * 0.08, breathingWeight);

                    if (head) {
                        // M7: Blend micro-gesture + curiosity into head tracking
                        let microY = 0, microX = 0;
                        if (this.activeMicroGesture) {
                            const totalDur = 0.4;
                            const prog = 1 - (this.microGestureTimer / totalDur);
                            const w = Math.sin(prog * Math.PI);
                            if (this.activeMicroGesture === 'nod') microX = -w * 0.15;
                            else if (this.activeMicroGesture === 'shake') microY = w * 0.12;
                            else if (this.activeMicroGesture === 'tilt') { /* z-axis handled separately */ }
                            else if (this.activeMicroGesture === 'look_away') microY = w * 0.2;
                            else if (this.activeMicroGesture === 'double_take') { microX = -w * 0.1; microY = w * 0.15; }
                        }

                        let curiY = 0, curiX = 0;
                        if (this.curiosityStrength > 0 && camera) {
                            const headWorldPos = new THREE.Vector3();
                            this.vrm!.scene.getWorldPosition(headWorldPos);
                            const toCamera = new THREE.Vector3().subVectors(camera.position, headWorldPos).normalize();
                            // Transform direction to local space of the avatar to handle body rotations correctly
                            const localToCamera = toCamera.clone().applyQuaternion(this.vrm!.scene.quaternion.clone().invert());
                            const angleY = Math.atan2(-localToCamera.x, -localToCamera.z);
                            const angleX = -Math.atan2(localToCamera.y, Math.sqrt(localToCamera.x * localToCamera.x + localToCamera.z * localToCamera.z));

                            // Clamp angles to natural human head movement limits
                            const limitY = Math.PI / 4; // 45 deg
                            const limitX = Math.PI / 6; // 30 deg
                            curiY = THREE.MathUtils.clamp(angleY, -limitY, limitY) * this.curiosityStrength;
                            curiX = THREE.MathUtils.clamp(angleX, -limitX, limitX) * this.curiosityStrength;
                        }

                        const baseHeadY = Math.sin(t * 0.4) * 0.04;
                        const baseHeadX = Math.cos(t * 0.3) * 0.02;
                        const targetY = this.isZoomed ? THREE.MathUtils.lerp(baseHeadY, 0, this.zoomLerp) : baseHeadY;
                        const targetX = this.isZoomed ? THREE.MathUtils.lerp(baseHeadX, 0.1, this.zoomLerp) : baseHeadX;

                        head.rotation.y = THREE.MathUtils.lerp(head.rotation.y, targetY + microY + curiY, breathingWeight);
                        head.rotation.x = THREE.MathUtils.lerp(head.rotation.x, targetX + microX + curiX, breathingWeight);
                    }
                }
            }

            this.tposeWarningSystem.update(delta, this.isProceduralIdle);

            // Autonomous will is updated via movementEngine.update
        }
    }

    public async nuclearReset() {
        if (!this.vrm || !this.mixer) return;

        // Stop all current animations
        this.mixer.stopAllAction();
        this.currentAction = null;
        this.isProceduralIdle = false;

        // Force pose reset
        if (this.vrm.humanoid) {
            this.vrm.humanoid.resetPose();
        }

        // CRITICAL: resetPose() puts the avatar in T-pose (VRM default).
        // We must immediately apply A-pose (arms at ~45° down) to avoid
        // the TposeWarningSystem re-detecting T-pose and triggering another reset.
        const lArm = this.bones['leftUpperArm'];
        const rArm = this.bones['rightUpperArm'];
        if (lArm) lArm.rotation.z = 1.35;   // ~77° — natural A-pose
        if (rArm) rArm.rotation.z = -1.35;  // ~-77° — natural A-pose

        // Also give spine/chest a slight natural curve to avoid rigid T-pose look
        const spine = this.bones['spine'];
        const chest = this.bones['chest'];
        if (spine) spine.rotation.x = -0.02;
        if (chest) chest.rotation.x = 0.03;

        this.vrm.scene.updateMatrixWorld(true);

        // Reset the T-pose warning system so it doesn't immediately re-detect
        this.tposeWarningSystem.reset();

        (window as any).log?.('Avatar System: Nuclear Reset → A-pose applied, warnings cleared.', 'var(--neon-blue)');

        // FIX: Force-clear the restoration lock before calling restoreModelIdle.
        // A concurrent call (e.g. from a previous reset chain) can leave isRestoringIdle=true,
        // which would cause restoreModelIdle() to silently return — leaving Jen frozen.
        this.isRestoringIdle = false;
        await this.restoreModelIdle(0.3);

        // If no idle animation was found, force procedural idle so she's never frozen
        if (!this.currentAction && !this.isProceduralIdle) {
            this.applyProceduralIdle();
            console.log('[Avatar] NuclearReset: No idle clips available, procedural idle active.');
        }
    }

    private sweepScene() {
        if (!this.scene) return;
        const toRemove: THREE.Object3D[] = [];
        this.scene.children.forEach((child) => {
            // Exclude the active VRM scene if it matches
            if (this.vrm && child === this.vrm.scene) return;

            if (
                child.name === 'VRM' ||
                child.userData.isAvatar ||
                (child.type === 'Group' && child.children.some(c => c.name === 'Root' || c.name === 'Armature'))
            ) {
                toRemove.push(child);
            }
        });
        toRemove.forEach((child) => {
            console.log('[Avatar] Sweeping duplicate/orphaned avatar scene child:', child.name || child.type);
            this.scene!.remove(child);
        });
    }

    private log(msg: string, color: string) {
        const isDevActive = (window as any).isDevModeActive === true;
        const isVerbose = msg.includes('MovementEngine:') ||
            msg.includes('Will:') ||
            msg.includes('[Avatar] Micro-gesture') ||
            msg.includes('[Avatar] Emotional state') ||
            msg.includes('Skeletal Link') ||
            msg.includes('Destination set') ||
            msg.includes('BlendShape') ||
            msg.includes('Haptic');

        if (isVerbose) {
            console.log(`[AVATAR DEBUG] ${msg}`);
            if (!isDevActive) {
                return;
            }
        }
        (window as any).log?.(msg, color);
    }
}
