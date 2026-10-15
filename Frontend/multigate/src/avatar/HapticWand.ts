import * as THREE from 'three';
import { VRM } from '@pixiv/three-vrm';

// ─────────────────────────────────────────────────────────────────────────────
// HAPTIC WAND v2 — OMEGA_362
// - Lumax cyan glowing tube with elastic, jelly-like sway (spring physics)
// - Extends TOWARDS the user's body (negative Z + arm-extension sleeve)
// - Squishy rubber-friction sound via Web Audio API (no file needed)
// - Precise VRM bone-sphere collision (no stutter from mesh raycasting)
// - 80s romantic synth beat on first contact per session
// ─────────────────────────────────────────────────────────────────────────────

const CYAN      = 0x00f3ff;
export const CYAN_STR  = '#00f3ff';

// ── Spring physics constants ─────────────────────────────────────────────────
const SPRING_K       = 28;   // stiffness  (higher = stiffer)
const SPRING_DAMPING = 5.8;  // damping    (lower = more jelly wobble)
const MAX_TIP_DEFLECT = 0.18; // max tip displacement from rest (m)

// ── VRM body sphere colliders (bone + radius in metres) ─────────────────────
// Deliberately generous but NOT overlapping, so the wand only fires INSIDE the skin.
const VRM_COLLIDERS: Array<{ bone: string; radius: number; zone: string }> = [
    { bone: 'head',           radius: 0.12, zone: 'head'     },
    { bone: 'neck',           radius: 0.065, zone: 'neck'    },
    { bone: 'upperChest',     radius: 0.16, zone: 'chest'    },
    { bone: 'chest',          radius: 0.15, zone: 'chest'    },
    { bone: 'spine',          radius: 0.12, zone: 'waist'    },
    { bone: 'hips',           radius: 0.14, zone: 'hips'     },
    { bone: 'leftShoulder',   radius: 0.07, zone: 'shoulder' },
    { bone: 'rightShoulder',  radius: 0.07, zone: 'shoulder' },
    { bone: 'leftUpperArm',   radius: 0.055, zone: 'arm'     },
    { bone: 'rightUpperArm',  radius: 0.055, zone: 'arm'     },
    { bone: 'leftLowerArm',   radius: 0.045, zone: 'arm'     },
    { bone: 'rightLowerArm',  radius: 0.045, zone: 'arm'     },
    { bone: 'leftHand',       radius: 0.055, zone: 'hand'    },
    { bone: 'rightHand',      radius: 0.055, zone: 'hand'    },
    { bone: 'leftUpperLeg',   radius: 0.085, zone: 'thigh'   },
    { bone: 'rightUpperLeg',  radius: 0.085, zone: 'thigh'   },
    { bone: 'leftLowerLeg',   radius: 0.055, zone: 'leg'     },
    { bone: 'rightLowerLeg',  radius: 0.055, zone: 'leg'     },
];

// ─────────────────────────────────────────────────────────────────────────────
// AUDIO UTILITIES
// ─────────────────────────────────────────────────────────────────────────────

function getAudioCtx(): AudioContext | null {
    const ctx = (window as any).foveaiAudioContext as AudioContext | null;
    if (!ctx || ctx.state === 'closed') return null;
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    return ctx;
}

/** Generates a continuous rubber-friction squeak (oscillating band-pass noise). */
function startSquishSound(): { stop: () => void } | null {
    const ctx = getAudioCtx();
    if (!ctx) return null;
    try {
        const bufLen = ctx.sampleRate * 0.5;
        const buf = ctx.createBuffer(1, bufLen, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < bufLen; i++) d[i] = Math.random() * 2 - 1;

        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.loop = true;

        // Band-pass around 900 Hz gives a rubbery squeak character
        const bp = ctx.createBiquadFilter();
        bp.type = 'bandpass';
        bp.frequency.value = 900;
        bp.Q.value = 4.5;

        // LFO to modulate frequency → gives "rubbing" oscillation
        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.frequency.value = 6;
        lfoGain.gain.value = 320;
        lfo.connect(lfoGain);
        lfoGain.connect(bp.frequency);
        lfo.start();

        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.045, ctx.currentTime + 0.06);

        src.connect(bp);
        bp.connect(gain);
        gain.connect(ctx.destination);
        src.start();

        return {
            stop: () => {
                try {
                    gain.gain.setTargetAtTime(0, ctx.currentTime, 0.04);
                    setTimeout(() => { try { src.stop(); lfo.stop(); } catch(_) {} }, 200);
                } catch (_) {}
            }
        };
    } catch (_) { return null; }
}

/** One-shot 80s romantic synth beat (synth pad + snare + cheesy bass). */
let _beat80sPlayed = false;
export function play80sBeat(): void {
    if (_beat80sPlayed) return;
    const ctx = getAudioCtx();
    if (!ctx) return;
    _beat80sPlayed = true;

    const t = ctx.currentTime;
    const masterGain = ctx.createGain();
    masterGain.gain.setValueAtTime(0.35, t);
    masterGain.connect(ctx.destination);

    // ── Synth pad: warm detuned chord (D minor → F → A) ──────────────────
    [[146.83, 174.61, 220.0], [196.0, 233.08, 293.66]].forEach((chord, ci) => {
        chord.forEach(freq => {
            const osc = ctx.createOscillator();
            const g = ctx.createGain();
            osc.type = 'sawtooth';
            osc.frequency.value = freq;
            osc.detune.value = (Math.random() - 0.5) * 12;
            g.gain.setValueAtTime(0, t + ci * 1.8);
            g.gain.linearRampToValueAtTime(0.08, t + ci * 1.8 + 0.3);
            g.gain.linearRampToValueAtTime(0.05, t + ci * 1.8 + 1.4);
            g.gain.linearRampToValueAtTime(0, t + ci * 1.8 + 2.4);
            osc.connect(g);
            g.connect(masterGain);
            osc.start(t + ci * 1.8);
            osc.stop(t + ci * 1.8 + 2.4);
        });
    });

    // ── Cheesy 80s bass (sine + slight square blend) ──────────────────────
    [[0, 73.42], [0.5, 73.42], [1.0, 65.41], [1.5, 73.42],
     [1.8, 87.31], [2.3, 65.41], [3.0, 73.42], [3.5, 65.41]].forEach(([when, freq]) => {
        const osc = ctx.createOscillator();
        const sq  = ctx.createOscillator();
        const g   = ctx.createGain();
        osc.type = 'sine'; osc.frequency.value = freq;
        sq.type = 'square'; sq.frequency.value = freq;
        const sqG = ctx.createGain(); sqG.gain.value = 0.05;
        g.gain.setValueAtTime(0, t + when);
        g.gain.linearRampToValueAtTime(0.22, t + when + 0.02);
        g.gain.linearRampToValueAtTime(0.10, t + when + 0.15);
        g.gain.linearRampToValueAtTime(0, t + when + 0.45);
        sq.connect(sqG); sqG.connect(g);
        osc.connect(g); g.connect(masterGain);
        osc.start(t + when); osc.stop(t + when + 0.5);
        sq.start(t + when); sq.stop(t + when + 0.5);
    });

    // ── 80s gated snare (noise burst with characteristic short gate) ──────
    [0.75, 1.5, 2.25, 3.0, 3.75].forEach(when => {
        const bufLen = Math.floor(ctx.sampleRate * 0.18);
        const buf = ctx.createBuffer(1, bufLen, ctx.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < bufLen; i++) data[i] = Math.random() * 2 - 1;
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const hp = ctx.createBiquadFilter();
        hp.type = 'highpass'; hp.frequency.value = 1800;
        const snrG = ctx.createGain();
        snrG.gain.setValueAtTime(0.55, t + when);
        snrG.gain.linearRampToValueAtTime(0, t + when + 0.08); // short gate
        src.connect(hp); hp.connect(snrG); snrG.connect(masterGain);
        src.start(t + when); src.stop(t + when + 0.18);
    });

    // ── Hi-hat tick ──────────────────────────────────────────────────────
    [0, 0.375, 0.75, 1.125, 1.5, 1.875, 2.25, 2.625, 3.0, 3.375, 3.75].forEach(when => {
        const bufLen = Math.floor(ctx.sampleRate * 0.04);
        const buf = ctx.createBuffer(1, bufLen, ctx.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < bufLen; i++) data[i] = Math.random() * 2 - 1;
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const hp = ctx.createBiquadFilter();
        hp.type = 'highpass'; hp.frequency.value = 8000;
        const hhG = ctx.createGain();
        hhG.gain.setValueAtTime(0.12, t + when);
        hhG.gain.linearRampToValueAtTime(0, t + when + 0.04);
        src.connect(hp); hp.connect(hhG); hhG.connect(masterGain);
        src.start(t + when); src.stop(t + when + 0.04);
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// HAPTIC WAND CLASS
// ─────────────────────────────────────────────────────────────────────────────

export class HapticWand {
    // The rod mesh (cylinder, elastic spring tip)
    public mesh: THREE.Group;
    private rodMesh: THREE.Mesh;
    private rodMaterial: THREE.MeshStandardMaterial;

    // Sleeve that extends toward user body (negative Z, arm direction)
    private sleeveMesh: THREE.Mesh;

    // Glow point at tip
    private tipGlow: THREE.Mesh;
    private tipLight: THREE.PointLight;

    private parent: THREE.Object3D;

    public active: boolean = false;
    public gamepad: Gamepad | null = null;

    // Spring physics state for tip sway
    private restTip: THREE.Vector3 = new THREE.Vector3();       // world position of rigid tip
    private springTip: THREE.Vector3 = new THREE.Vector3();     // physics-displaced tip
    private springVel: THREE.Vector3 = new THREE.Vector3();     // velocity

    private _tmpA = new THREE.Vector3();
    private _tmpB = new THREE.Vector3();
    private _tmpQ = new THREE.Quaternion();

    // Collision state
    private isContacting = false;
    private squishHandle: { stop: () => void } | null = null;
    private contactPressure = 0;          // smoothed 0–1

    // Frame throttle for bone-sphere test
    private _frame = 0;

    // Rod geometry constants
    private readonly ROD_LEN    = 0.52;  // forward tip length (m)
    private readonly SLEEVE_LEN = 0.20;  // backward sleeve length (m)

    constructor(parent: THREE.Object3D, _colorUnused?: number) {
        this.parent = parent;
        this.mesh = new THREE.Group();

        // ── Rod (pointing forward, -Z) ──────────────────────────────────────
        const rodGeo = new THREE.CylinderGeometry(0.006, 0.012, 1, 10);
        this.rodMaterial = new THREE.MeshStandardMaterial({
            color: CYAN,
            emissive: CYAN,
            emissiveIntensity: 1.8,
            transparent: true,
            opacity: 0.72,
            roughness: 0.2,
            metalness: 0.5,
            depthWrite: false,
        });
        this.rodMesh = new THREE.Mesh(rodGeo, this.rodMaterial);
        this.rodMesh.scale.set(1, this.ROD_LEN, 1);
        // Offset so base at local origin, tip at (0,0,-ROD_LEN)
        this.rodMesh.position.set(0, 0, -this.ROD_LEN * 0.5);
        this.rodMesh.quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 1, 0),
            new THREE.Vector3(0, 0, -1)
        );
        this.rodMesh.renderOrder = 998;
        this.mesh.add(this.rodMesh);

        // ── Sleeve (pointing backward toward the arm, +Z) ──────────────────
        const sleeveGeo = new THREE.CylinderGeometry(0.012, 0.018, 1, 10);
        const sleeveMat = new THREE.MeshStandardMaterial({
            color: CYAN,
            emissive: CYAN,
            emissiveIntensity: 0.8,
            transparent: true,
            opacity: 0.35,
            roughness: 0.3,
            metalness: 0.6,
            depthWrite: false,
        });
        this.sleeveMesh = new THREE.Mesh(sleeveGeo, sleeveMat);
        this.sleeveMesh.scale.set(1, this.SLEEVE_LEN, 1);
        this.sleeveMesh.position.set(0, 0, this.SLEEVE_LEN * 0.5);
        this.sleeveMesh.quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 1, 0),
            new THREE.Vector3(0, 0, 1)
        );
        this.sleeveMesh.renderOrder = 998;
        this.mesh.add(this.sleeveMesh);

        // ── Tip glow dot ────────────────────────────────────────────────────
        const glowGeo = new THREE.SphereGeometry(0.018, 10, 8);
        const glowMat = new THREE.MeshBasicMaterial({
            color: CYAN,
            transparent: true,
            opacity: 0.85,
            depthTest: false,
            depthWrite: false,
        });
        this.tipGlow = new THREE.Mesh(glowGeo, glowMat);
        this.tipGlow.position.set(0, 0, -this.ROD_LEN);
        this.tipGlow.renderOrder = 999;
        this.mesh.add(this.tipGlow);

        // ── Point light at tip ──────────────────────────────────────────────
        this.tipLight = new THREE.PointLight(CYAN, 0, 0.8);
        this.tipLight.position.set(0, 0, -this.ROD_LEN);
        this.mesh.add(this.tipLight);

        this.mesh.visible = false;
        parent.add(this.mesh);
    }

    // ── Hide/show the physical controller model when wand is active ─────────
    private _setControllerModelVisible(visible: boolean) {
        this.parent.traverse(child => {
            if (child === this.mesh || this.mesh.children.includes(child)) return;
            if (child instanceof THREE.Mesh || child instanceof THREE.Group) {
                if (child.name !== 'laser_pointer_left' && child.name !== 'laser_pointer_right') {
                    child.visible = visible;
                }
            }
        });
    }

    public setActive(val: boolean) {
        this.active = val;
        this.mesh.visible = val;
        this._setControllerModelVisible(!val);

        if (val) {
            this.rodMaterial.emissiveIntensity = 1.8;
            this.tipLight.intensity = 1.2;
            // Seed spring tip at rigid position
            this.parent.getWorldPosition(this._tmpA);
            this.parent.getWorldQuaternion(this._tmpQ);
            this.restTip.set(0, 0, -this.ROD_LEN).applyQuaternion(this._tmpQ).add(this._tmpA);
            this.springTip.copy(this.restTip);
            this.springVel.set(0, 0, 0);
        } else {
            this.rodMaterial.emissiveIntensity = 0;
            this.tipLight.intensity = 0;
            this._stopSquish();
        }
    }

    // ── Spring-physics tip sway ─────────────────────────────────────────────
    private _updateSpring(dt: number) {
        // Clamp delta to avoid large explosions on tab-switch
        const d = Math.min(dt, 0.05);

        // Calculate current rigid tip world position
        this.parent.getWorldPosition(this._tmpA);
        this.parent.getWorldQuaternion(this._tmpQ);
        this.restTip.set(0, 0, -this.ROD_LEN).applyQuaternion(this._tmpQ).add(this._tmpA);

        // Spring: F = -k*(x - rest) - damping*vel
        this._tmpB.subVectors(this.springTip, this.restTip);    // displacement
        const springF = this._tmpB.clone().multiplyScalar(-SPRING_K);
        const dampF   = this.springVel.clone().multiplyScalar(-SPRING_DAMPING);
        const accel   = springF.add(dampF);

        this.springVel.addScaledVector(accel, d);
        this.springTip.addScaledVector(this.springVel, d);

        // Clamp maximum deflection
        const disp = this.springTip.clone().sub(this.restTip);
        if (disp.length() > MAX_TIP_DEFLECT) {
            disp.normalize().multiplyScalar(MAX_TIP_DEFLECT);
            this.springTip.copy(this.restTip).add(disp);
        }
    }

    // ── Orient rod mesh to track spring tip ────────────────────────────────
    private _orientRodToTip() {
        this.parent.getWorldPosition(this._tmpA);  // base world pos

        // Local tip vector (world → local)
        const localTip = this.springTip.clone().sub(this._tmpA);
        // Convert to parent-local space
        const invParentQ = this.parent.getWorldQuaternion(new THREE.Quaternion()).invert();
        localTip.applyQuaternion(invParentQ);

        const len = localTip.length();
        const dir = localTip.clone().normalize();

        // Scale rod
        this.rodMesh.scale.set(1, len, 1);

        // Aim rod from origin toward dir
        const up = new THREE.Vector3(0, 1, 0);
        const q  = new THREE.Quaternion().setFromUnitVectors(up, dir);
        this.rodMesh.quaternion.copy(q);
        this.rodMesh.position.copy(dir.clone().multiplyScalar(len * 0.5));

        // Move tip glow to local tip
        this.tipGlow.position.copy(localTip);
        this.tipLight.position.copy(localTip);
    }

    // ── Bone-sphere collision (no raycasting = no stutter) ──────────────────
    private _checkCollision(vrm: VRM): { zone: string; pressure: number } | null {
        const tipWorld = this.springTip.clone();

        let bestPressure = 0;
        let bestZone = '';

        for (const col of VRM_COLLIDERS) {
            const boneNode = vrm.humanoid.getNormalizedBoneNode(col.bone as any);
            if (!boneNode) continue;
            const boneWorld = new THREE.Vector3();
            boneNode.getWorldPosition(boneWorld);
            const dist = tipWorld.distanceTo(boneWorld);
            if (dist < col.radius) {
                // Pressure = how deep inside the sphere (0 at edge, 1 at centre)
                const p = 1.0 - dist / col.radius;
                if (p > bestPressure) {
                    bestPressure = p;
                    bestZone = col.zone;
                }
            }
        }

        return bestPressure > 0.02 ? { zone: bestZone, pressure: bestPressure } : null;
    }

    // ── Audio helpers ───────────────────────────────────────────────────────
    private _startSquish() {
        if (this.squishHandle) return;
        this.squishHandle = startSquishSound();
    }
    private _stopSquish() {
        if (this.squishHandle) { this.squishHandle.stop(); this.squishHandle = null; }
    }

    // ── Main update ─────────────────────────────────────────────────────────
    public update(
        delta: number,
        vrm: VRM | null,
        onTouch?: (point: THREE.Vector3, pressure: number, zone: string) => void
    ) {
        if (!this.active) return;

        this._updateSpring(delta);
        this._orientRodToTip();

        // Contact pressure smoothing
        this._frame++;
        let collision: { zone: string; pressure: number } | null = null;

        if (vrm && this._frame % 2 === 0) {
            collision = this._checkCollision(vrm);
        }

        if (collision) {
            const { zone, pressure } = collision;
            // Smooth pressure
            this.contactPressure = THREE.MathUtils.lerp(this.contactPressure, pressure, 0.25);

            // Glow
            this.rodMaterial.emissiveIntensity = 2.5 + this.contactPressure * 14;
            this.tipLight.intensity = 2.5 + this.contactPressure * 6;

            // Push spring tip back (resistance force = "squish" sensation)
            const pushBack = this.contactPressure * 0.08;
            this.parent.getWorldQuaternion(this._tmpQ);
            const pushDir = new THREE.Vector3(0, 0, 1).applyQuaternion(this._tmpQ); // +Z = toward controller
            this.springVel.addScaledVector(pushDir, pushBack);

            // Squish sound
            this._startSquish();

            // Haptic
            this._fireHaptic(this.contactPressure);

            if (!this.isContacting) {
                this.isContacting = true;
                play80sBeat();
                if (onTouch) onTouch(this.springTip.clone(), this.contactPressure, zone);
            } else if (onTouch && this._frame % 60 === 0) {
                // Refresh zone every ~1s so gaze/expression keep updating
                onTouch(this.springTip.clone(), this.contactPressure, zone);
            }
        } else {
            this.contactPressure = THREE.MathUtils.lerp(this.contactPressure, 0, 0.15);
            this.rodMaterial.emissiveIntensity = THREE.MathUtils.lerp(
                this.rodMaterial.emissiveIntensity, 1.8, 0.1
            );
            this.tipLight.intensity = THREE.MathUtils.lerp(this.tipLight.intensity, 1.2, 0.1);
            if (this.isContacting) {
                this.isContacting = false;
                this._stopSquish();
            }
        }
    }

    private _fireHaptic(pressure: number) {
        let haptic: any = null;
        if (this.gamepad) {
            haptic = this.gamepad.hapticActuators?.[0] || this.gamepad.vibrationActuator;
        } else {
            const inputSource = (this.parent as any).userData?.inputSource;
            if (inputSource?.gamepad) {
                haptic = inputSource.gamepad.hapticActuators?.[0] || inputSource.gamepad.vibrationActuator;
            }
        }
        if (!haptic) return;
        const intensity = Math.min(1.0, pressure * 1.1);
        const duration  = 14 + Math.floor(pressure * 10);
        try {
            if (typeof haptic.pulse === 'function') {
                haptic.pulse(intensity, duration);
            } else if (typeof haptic.playEffect === 'function') {
                haptic.playEffect('dual-rumble', {
                    startDelay: 0, duration,
                    weakMagnitude: intensity * 0.6,
                    strongMagnitude: intensity
                }).catch(() => {});
            }
        } catch (_) {}
    }
}
