using System;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.Avatar;

namespace FoveAI.Avatar
{
    /// <summary>
    /// TposeWarningSystem — Ported from Frontend/XR_Vessel/src/avatar/TposeWarningSystem.ts
    /// Detects when a VRM avatar is frozen in T-pose and triggers auto-recovery.
    ///
    /// A dedicated system for detecting and warning about T-pose conditions in avatars.
    /// Provides clear indicators when an avatar is stuck in T-pose, which is an error state.
    /// Auto-triggers nuclearReset() with a 15-second cooldown to prevent death loops.
    /// </summary>
    public class TposeWarningSystem : MonoBehaviour
    {
        [Header("Detection")]
        public float detectionThreshold = 8.0f;     // seconds before T-pose is confirmed
        public float checkInterval = 2.0f;          // seconds between checks
        public int maxErrorCount = 3;
        public float armThreshold = 0.5f;            // radians
        public float legThreshold = 0.2f;            // radians
        public float positionChangeThreshold = 0.01f; // min rotation change to consider movement
        public float autoRecoveryCooldown = 15.0f;   // seconds between auto-recoveries

        [Header("Status (Read-only)")]
        public bool isCritical;
        public int errorCount;
        public bool warningShown;
        public float detectionTimer;
        public bool tposeDetected;

        // ── Internal state ──
        private Animator _animator;
        private VRMAvatarLoader _avatarLoader;
        private float _lastCheckTime;
        private float _lastAutoRecovery;
        private bool _proceduralIdleActive;

        // Bone movement tracking
        private readonly Dictionary<HumanBodyBones, Vector3> _lastBoneRotations = new();

        // Bones to monitor
        private static readonly HumanBodyBones[] MONITORED_BONES =
        {
            HumanBodyBones.RightUpperArm, HumanBodyBones.LeftUpperArm,
            HumanBodyBones.RightUpperLeg, HumanBodyBones.LeftUpperLeg,
            HumanBodyBones.Spine, HumanBodyBones.Chest,
            HumanBodyBones.Neck, HumanBodyBones.Head
        };

        // ── Public API ──

        /// <summary>Set whether procedural idle is active (suppresses T-pose warnings).</summary>
        public void SetProceduralIdle(bool active)
        {
            _proceduralIdleActive = active;
            if (active)
            {
                detectionTimer = 0f;
                warningShown = false;
                isCritical = false;
            }
        }

        /// <summary>Update the T-pose warning system. Returns true if T-pose is detected.</summary>
        public bool UpdateSystem(float delta)
        {
            if (_animator == null)
            {
                TryFindAnimator();
                if (_animator == null) return false;
            }

            // Procedural idle suppresses T-pose warnings
            if (_proceduralIdleActive)
            {
                detectionTimer = 0f;
                warningShown = false;
                isCritical = false;
                return false;
            }

            _lastCheckTime += delta;

            // Only check every checkInterval seconds
            if (_lastCheckTime < checkInterval)
                return isCritical;

            _lastCheckTime = 0f;

            // Check if any animation is playing
            bool hasAnimation = _animator.runtimeAnimatorController != null &&
                                _animator.GetCurrentAnimatorStateInfo(0).length > 0f;

            if (!hasAnimation)
            {
                detectionTimer += checkInterval;

                if (detectionTimer >= detectionThreshold)
                {
                    var (isTpose, reason) = CheckForTpose();

                    if (isTpose)
                    {
                        errorCount++;
                        warningShown = true;
                        tposeDetected = true;
                        FoveAI.DebugOverlay.QuestDebugOverlay.Log(
                            $"[TposeWatch] T-POSE DETECTED — {reason}");

                        // Auto-recovery with cooldown
                        if (Time.time - _lastAutoRecovery > autoRecoveryCooldown)
                        {
                            _lastAutoRecovery = Time.time;
                            FoveAI.DebugOverlay.QuestDebugOverlay.Log(
                                "[TposeWatch] Initiating auto-recovery...");
                            TriggerRecovery();
                        }
                        else
                        {
                            FoveAI.DebugOverlay.QuestDebugOverlay.Log(
                                "[TposeWatch] Auto-recovery cooldown active — skipping");
                        }

                        if (errorCount >= maxErrorCount)
                        {
                            isCritical = true;
                            FoveAI.DebugOverlay.QuestDebugOverlay.Log(
                                "[TposeWatch] CRITICAL T-POSE — needs manual intervention");
                        }

                        return true;
                    }
                    else
                    {
                        // Bone positions don't indicate T-pose — reset timer
                        detectionTimer = 0f;
                        tposeDetected = false;
                    }
                }
            }
            else
            {
                // Animation is playing — reset detection state
                detectionTimer = 0f;
                warningShown = false;
                isCritical = false;
                tposeDetected = false;
            }

            return isCritical;
        }

        /// <summary>Check if the avatar is objectively in T-pose by analyzing bone positions.</summary>
        private (bool isTpose, string reason) CheckForTpose()
        {
            if (_animator == null || !_animator.isHuman)
                return (true, "No humanoid available for bone analysis");

            var rightArm = _animator.GetBoneTransform(HumanBodyBones.RightUpperArm);
            var leftArm = _animator.GetBoneTransform(HumanBodyBones.LeftUpperArm);
            var rightLeg = _animator.GetBoneTransform(HumanBodyBones.RightUpperLeg);
            var leftLeg = _animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg);

            if (rightArm == null || leftArm == null || rightLeg == null || leftLeg == null)
                return (true, "Required bones not found for T-pose detection");

            // Check bone rotations
            float rArmRotX = rightArm.localRotation.x;
            float rArmRotZ = rightArm.localRotation.z;
            float lArmRotX = leftArm.localRotation.x;
            float lArmRotZ = leftArm.localRotation.z;
            float rLegRotX = rightLeg.localRotation.x;
            float lLegRotX = leftLeg.localRotation.x;

            // Arms in T-pose if both X and Z rotations are near zero
            bool armsInTpose =
                Mathf.Abs(rArmRotX) < armThreshold && Mathf.Abs(rArmRotZ) < armThreshold &&
                Mathf.Abs(lArmRotX) < armThreshold && Mathf.Abs(lArmRotZ) < armThreshold;

            bool legsInTpose =
                Mathf.Abs(rLegRotX) < legThreshold && Mathf.Abs(lLegRotX) < legThreshold;

            bool bonesMoving = CheckBoneMovement();

            if (armsInTpose && legsInTpose && !bonesMoving)
            {
                return (true,
                    $"Arms horizontal (R_Z:{rArmRotZ:F3}, L_Z:{lArmRotZ:F3}) " +
                    $"and legs vertical ({rLegRotX:F3}, {lLegRotX:F3}) " +
                    $"with no bone movement");
            }
            else if (armsInTpose && legsInTpose && bonesMoving)
            {
                return (false, "Arms near T-pose but bones ARE moving — alive/transitioning");
            }
            else
            {
                return (false,
                    $"Bone positions not in T-pose: arms_z({rArmRotZ:F3}, {lArmRotZ:F3}) " +
                    $"legs_x({rLegRotX:F3}, {lLegRotX:F3})");
            }
        }

        /// <summary>Check if bones are moving by comparing current rotations with last.</summary>
        private bool CheckBoneMovement()
        {
            if (_animator == null) return false;

            bool movementDetected = false;

            foreach (var boneName in MONITORED_BONES)
            {
                var bone = _animator.GetBoneTransform(boneName);
                if (bone == null) continue;

                // Use euler angles for comparison
                Vector3 currentRot = bone.localRotation.eulerAngles;

                if (_lastBoneRotations.TryGetValue(boneName, out var lastRot))
                {
                    float diffX = Mathf.Abs(Mathf.DeltaAngle(currentRot.x, lastRot.x));
                    float diffY = Mathf.Abs(Mathf.DeltaAngle(currentRot.y, lastRot.y));
                    float diffZ = Mathf.Abs(Mathf.DeltaAngle(currentRot.z, lastRot.z));

                    if (diffX > positionChangeThreshold * Mathf.Rad2Deg ||
                        diffY > positionChangeThreshold * Mathf.Rad2Deg ||
                        diffZ > positionChangeThreshold * Mathf.Rad2Deg)
                    {
                        movementDetected = true;
                        break;
                    }
                }

                _lastBoneRotations[boneName] = currentRot;
            }

            return movementDetected;
        }

        /// <summary>Trigger recovery — re-init the avatar or reset pose.</summary>
        private void TriggerRecovery()
        {
            if (_avatarLoader == null)
                _avatarLoader = FindAnyObjectByType<VRMAvatarLoader>();

            if (_avatarLoader != null && _avatarLoader.Avatar != null)
            {
                // Reset all humanoid bones to their default pose
                var anim = _avatarLoader.Avatar.GetComponentInChildren<Animator>();
                if (anim != null && anim.isHuman)
                {
                    // Re-write default muscle values
                    anim.WriteDefaultValues();
                    anim.Update(0f);
                    FoveAI.DebugOverlay.QuestDebugOverlay.Log("[TposeWatch] Avatar pose reset");
                }
            }
        }

        /// <summary>Get current status for diagnostics.</summary>
        public string GetStatusText()
        {
            return $"T-pose Watch: critical={isCritical} errors={errorCount}/{maxErrorCount} " +
                   $"timer={detectionTimer:F1}s detected={tposeDetected}";
        }

        /// <summary>Reset the T-pose warning system state.</summary>
        public void Reset()
        {
            detectionTimer = 0f;
            warningShown = false;
            errorCount = 0;
            isCritical = false;
            tposeDetected = false;
            _lastCheckTime = 0f;
            _lastBoneRotations.Clear();
            FoveAI.DebugOverlay.QuestDebugOverlay.Log("[TposeWatch] System reset — warnings cleared");
        }

        private void TryFindAnimator()
        {
            if (_avatarLoader == null)
                _avatarLoader = FindAnyObjectByType<VRMAvatarLoader>();
            if (_avatarLoader != null && _avatarLoader.Avatar != null)
                _animator = _avatarLoader.Avatar.GetComponentInChildren<Animator>();
        }

        private void Update()
        {
            UpdateSystem(Time.deltaTime);
        }
    }
}
