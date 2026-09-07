using System;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.Avatar;
using FoveAI.UI;

namespace FoveAI.XR
{
    /// <summary>
    /// XRHapticWand — Ported directly from Frontend/XR_Vessel/src/avatar/HapticWand.ts
    /// Double-clicking trigger transforms controller into an elastic, glowing rubbery stick
    /// with spring physics for tickling Alice, triggering playful tactile haptic vibration
    /// and sensitivity blendshape reactions.
    /// </summary>
    public class XRHapticWand : MonoBehaviour
    {
        public enum WandHand { Left, Right }
        public WandHand hand = WandHand.Right;

        [Header("Wand Visuals")]
        public float wandLength = 0.45f;
        public float wandRadius = 0.015f;
        public Color wandColor = new Color(0f, 0.95f, 1f, 0.9f); // Lumax Cyan

        private GameObject _wandRoot;
        private LineRenderer _wandLine;
        private Transform _tipTransform;

        private bool _isWandActive = false;
        public bool IsWandActive => _isWandActive;

        // Double-click trigger detection
        private float _lastTriggerTime = 0f;
        private const float DoubleClickThreshold = 0.35f;

        // Spring physics constants (ported from HapticWand.ts)
        private Vector3 _tipOffset = Vector3.zero;
        private Vector3 _tipVelocity = Vector3.zero;
        private const float SpringK = 28f;
        private const float SpringDamping = 5.8f;

        private AvatarBlendshapeDriver _blendshapeDriver;
        private Animator _avatarAnimator;

        private void Start()
        {
            BuildWandVisual();
        }

        private void BuildWandVisual()
        {
            _wandRoot = new GameObject("HapticWandVisual");
            _wandRoot.transform.SetParent(transform, false);

            _wandLine = _wandRoot.AddComponent<LineRenderer>();
            _wandLine.useWorldSpace = false;
            _wandLine.positionCount = 10;
            _wandLine.startWidth = wandRadius * 2f;
            _wandLine.endWidth = wandRadius * 2.8f; // Spherical squishy tip

            var mat = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            mat.color = wandColor;
            _wandLine.material = mat;

            var tipObj = new GameObject("WandTip");
            tipObj.transform.SetParent(_wandRoot.transform, false);
            tipObj.transform.localPosition = new Vector3(0, 0, wandLength);
            _tipTransform = tipObj.transform;

            _wandRoot.SetActive(false);
        }

        private void Update()
        {
            CheckTriggerToggle();

            if (_isWandActive)
            {
                UpdateSpringPhysics();
                CheckAvatarCollision();
            }
        }

        private void CheckTriggerToggle()
        {
            var controller = hand == WandHand.Left ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
            bool triggerDown = OVRInput.GetDown(OVRInput.Button.PrimaryIndexTrigger, controller);

            if (triggerDown)
            {
                float timeNow = Time.time;
                if (timeNow - _lastTriggerTime <= DoubleClickThreshold)
                {
                    ToggleWandMode();
                    _lastTriggerTime = 0f;
                }
                else
                {
                    _lastTriggerTime = timeNow;
                }
            }
        }

        public void ToggleWandMode()
        {
            _isWandActive = !_isWandActive;
            if (_wandRoot != null) _wandRoot.SetActive(_isWandActive);

            var controller = hand == WandHand.Left ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
            OVRInput.SetControllerVibration(0.8f, 0.8f, controller);
            Invoke(nameof(StopHaptics), 0.12f);

            string state = _isWandActive ? "ACTIVATED" : "DEACTIVATED";
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"🪄 Haptic Wand {state} ({hand})");
            XRIDEHud.FlashNotification($"🪄 HAPTIC WAND {state}", 2.5f);
        }

        private void StopHaptics()
        {
            var controller = hand == WandHand.Left ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
            OVRInput.SetControllerVibration(0f, 0f, controller);
        }

        private void UpdateSpringPhysics()
        {
            // Spring physics for rubbery elasticity
            float dt = Mathf.Min(Time.deltaTime, 0.033f);
            Vector3 springForce = -SpringK * _tipOffset;
            Vector3 dampingForce = -SpringDamping * _tipVelocity;
            Vector3 acc = springForce + dampingForce;

            _tipVelocity += acc * dt;
            _tipOffset += _tipVelocity * dt;
            _tipOffset = Vector3.ClampMagnitude(_tipOffset, 0.18f);

            // Compute curve points along the rubber stick
            Vector3 basePos = Vector3.zero;
            Vector3 targetTip = new Vector3(0, 0, wandLength) + _tipOffset;
            _tipTransform.localPosition = targetTip;

            for (int i = 0; i < 10; i++)
            {
                float t = i / 9f;
                // Quadratic bezier curve giving jelly bend
                Vector3 pt = Vector3.Lerp(basePos, targetTip, t) + _tipOffset * (Mathf.Sin(t * Mathf.PI) * 0.3f);
                _wandLine.SetPosition(i, pt);
            }
        }

        private void CheckAvatarCollision()
        {
            if (_avatarAnimator == null)
            {
                var avatarLoader = FindAnyObjectByType<VRMAvatarLoader>();
                if (avatarLoader != null && avatarLoader.Avatar != null)
                {
                    _avatarAnimator = avatarLoader.Avatar.GetComponentInChildren<Animator>();
                    _blendshapeDriver = avatarLoader.Avatar.GetComponent<AvatarBlendshapeDriver>();
                }
            }

            if (_avatarAnimator == null || !_avatarAnimator.isHuman) return;

            Vector3 tipWorldPos = _tipTransform.position;

            // Check contact against key sensitive bones (Head, Chest, Hips, Arms)
            HumanBodyBones[] sensitiveBones = {
                HumanBodyBones.Head,
                HumanBodyBones.Chest,
                HumanBodyBones.Spine,
                HumanBodyBones.Hips,
                HumanBodyBones.LeftUpperArm,
                HumanBodyBones.RightUpperArm
            };

            foreach (var bone in sensitiveBones)
            {
                Transform boneTransform = _avatarAnimator.GetBoneTransform(bone);
                if (boneTransform == null) continue;

                float dist = Vector3.Distance(tipWorldPos, boneTransform.position);
                float radius = bone == HumanBodyBones.Head ? 0.16f : 0.18f;

                if (dist < radius)
                {
                    // Contact registered: trigger tickle haptics and smile/blush reaction
                    var controller = hand == WandHand.Left ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
                    OVRInput.SetControllerVibration(0.4f, 0.3f, controller);

                    if (_blendshapeDriver != null)
                    {
                        _blendshapeDriver.ApplyEmotion("happy", 0.75f);
                    }
                    return;
                }
            }
        }
    }
}
