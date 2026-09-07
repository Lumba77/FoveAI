import * as THREE from 'three';
import { VRM } from '@pixiv/three-vrm';

/**
 * T-pose Warning System
 * A dedicated system for detecting and warning about T-pose conditions in avatars.
 * This system provides clear indicators when an avatar is stuck in T-pose,
 * which is considered an error state that needs to be resolved.
 */
export class TposeWarningSystem {
    private vrm: VRM | null = null;
    private mixer: THREE.AnimationMixer | null = null;
    private currentAction: THREE.AnimationAction | null = null;

    // Detection parameters
    private detectionTimer: number = 0;
    private detectionThreshold: number = 8.0; // Restored to 8s to prevent transition false-positive loops
    private warningShown: boolean = false;
    private errorCount: number = 0;
    private maxErrorCount: number = 3;
    private isCritical: boolean = false;
    private lastAnimationTime: number = 0;
    private lastCheckTime: number = 0;
    private checkInterval: number = 2.0; // seconds between checks

    // Bone position tracking
    private lastBonePositions: Map<string, THREE.Euler> = new Map();
    private positionChangeThreshold: number = 0.01; // minimum rotation change to consider movement

    /**
     * Initialize the T-pose warning system
     * @param vrm The VRM avatar instance
     * @param mixer The animation mixer instance
     */
    public initialize(vrm: VRM, mixer: THREE.AnimationMixer): void {
        this.vrm = vrm;
        this.mixer = mixer;
        this.reset();

        // Suppressed verbose init logging
    }

    /**
     * Set the current animation action
     * @param action The current animation action, or null if no animation is playing
     */
    public setCurrentAction(action: THREE.AnimationAction | null): void {
        this.currentAction = action;

        if (action) {
            this.lastAnimationTime = Date.now();
        }
    }

    /**
     * Update the T-pose warning system
     * @param delta Time since last update in seconds
     * @returns true if T-pose is detected, false otherwise
     */
    public update(delta: number, isProceduralIdle: boolean = false): boolean {
        if (!this.vrm || !this.mixer) {
            return false;
        }

        if (isProceduralIdle) {
            // Procedural idle is active, suppress T-pose warnings
            this.detectionTimer = 0;
            this.warningShown = false;
            this.isCritical = false;
            return false;
        }

        // Update check timer
        this.lastCheckTime += delta;

        // Only check every checkInterval seconds to avoid performance impact
        if (this.lastCheckTime < this.checkInterval) {
            return this.isCritical;
        }

        this.lastCheckTime = 0;

        // Check if we have a valid current action
        const hasAction = !!this.currentAction;
        const isRunning = hasAction && this.currentAction!.isRunning();

        if (!hasAction || !isRunning) {
            // No animation is playing - increment detection timer
            this.detectionTimer += this.checkInterval;

            // Check if we've exceeded the threshold
            if (this.detectionTimer >= this.detectionThreshold) {
                // Perform bone position analysis to confirm T-pose
                const tposeResult = this.checkForTpose();

                if (tposeResult.isTpose) {
                    this.errorCount++;
                    this.warningShown = true;

                    console.error(`[TposeWarningSystem] ❌ T-POSE DETECTED - ${tposeResult.reason}`);
                    
                    // AUTO RECOVERY TRIGGER (with cooldown to prevent death loop)
                    // nuclearReset() calls resetPose() which IS T-pose, so if we
                    // trigger it every check, we create an infinite reset→T-pose→reset loop.
                    // Cooldown: only auto-recover once every 15 seconds.
                    const now = Date.now();
                    const lastRecovery = (this as any)._lastAutoRecovery || 0;
                    if (now - lastRecovery > 15000) {
                        (this as any)._lastAutoRecovery = now;
                        if ((window as any).foveaiAvatar) {
                            console.warn('[TposeWarningSystem] Initiating Auto-Recovery (cooled down)...');
                            (window as any).foveaiAvatar.nuclearReset();
                        }
                    } else {
                        console.warn('[TposeWarningSystem] Auto-recovery cooldown active — skipping nuclearReset to avoid loop');
                    }

                    console.error(`[TposeWarningSystem] ❌ Error count: ${this.errorCount}/${this.maxErrorCount}`);

                    // Check if we've reached critical state
                    if (this.errorCount >= this.maxErrorCount) {
                        this.isCritical = true;
                        console.error('[TposeWarningSystem] 🚨 CRITICAL T-POSE ERROR - IMMEDIATE ATTENTION REQUIRED');
                        console.error('[TposeWarningSystem] 🚨 Avatar is stuck in T-pose and needs manual intervention');
                    }

                    return true;
                } else {
                    // Bone positions don't indicate T-pose
                    // Silently reset timer to avoid repeated warnings
                    this.detectionTimer = 0;
                }
            }
        } else {
            // Animation is playing - silently reset detection state
            this.detectionTimer = 0;
            this.warningShown = false;
            this.isCritical = false;
        }

        return this.isCritical;
    }

    /**
     * Check if the avatar is objectively in T-pose by analyzing bone positions
     * @returns Object with isTpose boolean and reason string
     */
    private checkForTpose(): { isTpose: boolean; reason: string } {
        if (!this.vrm?.humanoid) {
            return { isTpose: true, reason: 'No humanoid available for bone analysis' };
        }

        try {
            const humanoid = this.vrm.humanoid;

            // Get key bones for T-pose detection
            const rightArm = humanoid.getRawBoneNode('rightUpperArm');
            const leftArm = humanoid.getRawBoneNode('leftUpperArm');
            const rightLeg = humanoid.getRawBoneNode('rightUpperLeg');
            const leftLeg = humanoid.getRawBoneNode('leftUpperLeg');

            if (!rightArm || !leftArm || !rightLeg || !leftLeg) {
                return { isTpose: true, reason: 'Required bones not found for T-pose detection' };
            }

            // Check bone rotations - check both X and Z for a more robust detection
            const rightArmRotX = rightArm.rotation.x;
            const rightArmRotZ = rightArm.rotation.z;
            const leftArmRotX = leftArm.rotation.x;
            const leftArmRotZ = leftArm.rotation.z;
            
            const rightLegRotX = rightLeg.rotation.x;
            const leftLegRotX = leftLeg.rotation.x;

            // T-pose thresholds (arms horizontal, legs vertical)
            const armThreshold = 0.5; // radians
            const legThreshold = 0.2; // radians

            // Arms are in T-pose if BOTH X and Z rotations are near zero
            const armsInTpose = (Math.abs(rightArmRotX) < armThreshold && Math.abs(rightArmRotZ) < armThreshold) && 
                               (Math.abs(leftArmRotX) < armThreshold && Math.abs(leftArmRotZ) < armThreshold);
            
            const legsInTpose = Math.abs(rightLegRotX) < legThreshold && Math.abs(leftLegRotX) < legThreshold;

            // Check if bones are moving (not stuck)
            const bonesMoving = this.checkBoneMovement();

            if (armsInTpose && legsInTpose && !bonesMoving) {
                return {
                    isTpose: true,
                    reason: `Arms horizontal (R_Z:${rightArmRotZ.toFixed(3)}, L_Z:${leftArmRotZ.toFixed(3)}) ` +
                          `and legs vertical (${rightLegRotX.toFixed(3)}, ${leftLegRotX.toFixed(3)}) ` +
                          `with no bone movement detected`
                };
            } else if (armsInTpose && legsInTpose && bonesMoving) {
                // Bones ARE moving — the procedural idle or animation is working.
                // Arms near horizontal doesn't mean T-pose if the body is alive.
                return {
                    isTpose: false,
                    reason: `Arms near T-pose position but bones ARE moving — alive/transitioning`
                };
            } else {
                return {
                    isTpose: false,
                    reason: `Bone positions not in T-pose: arms_z(${rightArmRotZ.toFixed(3)}, ${leftArmRotZ.toFixed(3)}) ` +
                          `legs_x(${rightLegRotX.toFixed(3)}, ${leftLegRotX.toFixed(3)})`
                };
            }
        } catch (err) {
            console.warn('[TposeWarningSystem] Bone analysis error:', err);
            return { isTpose: false, reason: 'Bone analysis error - assuming normal pose' };
        }
    }

    /**
     * Check if bones are moving by comparing current positions with last positions
     * @returns true if bones are moving, false if they're stuck
     */
    private checkBoneMovement(): boolean {
        if (!this.vrm?.humanoid) {
            return false;
        }

        try {
            const humanoid = this.vrm.humanoid;
            const bones = [
                'rightUpperArm', 'leftUpperArm',
                'rightUpperLeg', 'leftUpperLeg',
                'spine', 'chest', 'neck', 'head'
            ];

            let movementDetected = false;

            for (const boneName of bones) {
                const bone = humanoid.getRawBoneNode(boneName as any);
                if (bone) {
                    const currentRot = bone.rotation.clone();

                    // Get previous rotation if available
                    const lastRot = this.lastBonePositions.get(boneName);

                    if (lastRot) {
                        // Calculate rotation difference
                        const diffX = Math.abs(currentRot.x - lastRot.x);
                        const diffY = Math.abs(currentRot.y - lastRot.y);
                        const diffZ = Math.abs(currentRot.z - lastRot.z);

                        // If any rotation component changed significantly, movement is detected
                        if (diffX > this.positionChangeThreshold ||
                            diffY > this.positionChangeThreshold ||
                            diffZ > this.positionChangeThreshold) {
                            movementDetected = true;
                            break;
                        }
                    }

                    // Store current rotation for next check
                    this.lastBonePositions.set(boneName, currentRot);
                }
            }

            return movementDetected;
        } catch (err) {
            console.warn('[TposeWarningSystem] Bone movement check error:', err);
            return true; // Assume movement if we can't check
        }
    }

    /**
     * Get the current status of the T-pose warning system
     * @returns Status object with error information
     */
    public getStatus(): {
        isCritical: boolean;
        errorCount: number;
        lastAnimationTime: number;
        warningShown: boolean;
        detectionTimer: number;
    } {
        return {
            isCritical: this.isCritical,
            errorCount: this.errorCount,
            lastAnimationTime: this.lastAnimationTime,
            warningShown: this.warningShown,
            detectionTimer: this.detectionTimer
        };
    }

    /**
     * Reset the T-pose warning system state
     */
    public reset(): void {
        this.detectionTimer = 0;
        this.warningShown = false;
        this.errorCount = 0;
        this.isCritical = false;
        this.lastAnimationTime = Date.now();
        this.lastCheckTime = 0;
        this.lastBonePositions.clear();

        console.log('[TposeWarningSystem] System reset - all warnings cleared');
    }

    /**
     * Get detailed diagnostic information about the current state
     * @returns Diagnostic information including bone positions
     */
    public getDiagnostics(): {
        status: { isCritical: boolean; errorCount: number; lastAnimationTime: number; warningShown: boolean; detectionTimer: number; };
        bonePositions: Record<string, { rotation: THREE.Euler, position: THREE.Vector3 }>;
        currentAction: string | null;
    } {
        const diagnostics: any = {
            status: this.getStatus(),
            bonePositions: {},
            currentAction: this.currentAction ? this.currentAction.getClip().name : null
        };

        if (this.vrm?.humanoid) {
            const bones = [
                'rightUpperArm', 'leftUpperArm',
                'rightUpperLeg', 'leftUpperLeg',
                'spine', 'chest', 'neck', 'head'
            ];

            for (const boneName of bones) {
                const bone = this.vrm.humanoid.getRawBoneNode(boneName as any);
                if (bone) {
                    diagnostics.bonePositions[boneName] = {
                        rotation: bone.rotation.clone(),
                        position: bone.position.clone()
                    };
                }
            }
        }

        return diagnostics;
    }
}