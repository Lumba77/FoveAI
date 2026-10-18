using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.XR;

namespace FoveAI.XR
{
    /// <summary>
    /// QuestControllerRide — the controller button ride (FoveAI house ride):
    ///
    ///   Left  Y        → Jen snapshot (photo of Jen, her POV-adjacent frame)
    ///   Left  X        → Debug window toggle in scene (QuestDebugOverlay)
    ///   Right A        → User snapshot (photo, user's view)
    ///   Right B        → PTT / toggle listen (VAD manual recording toggle)
    ///   Double grip    → toggle User Overtake Avatar Steering (drives Jen)
    ///   Double trigger → magic wands fun feature toggle (XRHapticWand)
    ///   Long held grip → grab + carry objects (one or two hands)
    ///
    /// FUI language: colors only signal state/identity; the ride signals by
    /// haptics, not decoration.
    /// </summary>
    public class QuestControllerRide : MonoBehaviour
    {
        [Header("Ride thresholds")]
        public float doubleClickWindow = 0.45f;   // s — double grip/trigger window
        public float longGripHold = 0.6f;         // s — long-held grip to grab
        public float grabRadius = 1.2f;           // m — reach for prop grab
        public float snapshotRes = 1280f;         // px — photo long edge

        private string _snapDir;
        private float _lastGripDown = -10f;
        private float _lastTriggerDown = -10f;
        private bool _overtakeSteering;
        private XRHapticWand[] _wands;
        private float _hapticPulseTime;

        // carried prop book-keeping — grip release restores dynamics
        private class CarriedProp
        {
            public Rigidbody body;
            public Transform controller;
            public Vector3 localPos;
            public Quaternion localRot;
            public bool wasKinematic;
            public bool useGravity;
        }
        private readonly List<CarriedProp> _carried = new List<CarriedProp>();

        private void Awake()
        {
            _snapDir = Path.Combine(Application.persistentDataPath, "Snapshots");
            Directory.CreateDirectory(_snapDir);
        }

        private void Update()
        {
            if (OVRInput.IsControllerConnected(OVRInput.Controller.LTouch))
                PollLeft();
            if (OVRInput.IsControllerConnected(OVRInput.Controller.RTouch))
                PollRight();
            PollGripsAndTriggers();
        }

        // ── left hand ──
        private void PollLeft()
        {
            if (OVRInput.GetDown(OVRInput.Button.Four, OVRInput.Controller.LTouch))
                CaptureSnapshot(jen: true);                 // Y → Jen snapshot
            if (OVRInput.GetDown(OVRInput.Button.Three, OVRInput.Controller.LTouch))
                ToggleDebugWindow();                        // X → debug window
        }

        // ── right hand ──
        private void PollRight()
        {
            if (OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch))
                CaptureSnapshot(jen: false);                // A → user snapshot
            if (OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch))
                TogglePtt();                                // B → PTT / listen toggle
        }

        // ── the doubles + the long-held grip ──
        private void PollGripsAndTriggers()
        {
            bool gripDown = OVRInput.GetDown(OVRInput.Button.PrimaryHandTrigger);
            if (gripDown && !_gripLatched)
            {
                _gripLatched = true;
                if (Time.unscaledTime - _lastGripDown < doubleClickWindow)
                {
                    ToggleOvertakeSteering();               // double grip
                    _lastGripDown = -10f;
                    _gripHoldStart = -1f;
                    return;
                }
                _lastGripDown = Time.unscaledTime;
                _gripHoldStart = Time.unscaledTime;         // long-hold begins
            }
            if (!gripDown && _gripLatched)
            {
                _gripLatched = false;
                if (_carried.Count > 0) ReleaseProps();     // grip release → drop
                else if (_gripHoldStart > 0
                    && Time.unscaledTime - _gripHoldStart < longGripHold) { /* tap */ }
                _gripHoldStart = -1f;
            }
            // long-held: one OR two hands grip → grab/carry
            if (_gripHoldStart > 0 && _carried.Count == 0
                && Time.unscaledTime - _gripHoldStart >= longGripHold)
            {
                TryGrabProps();
                _gripHoldStart = -1f;
            }

            bool triggerDown = OVRInput.Get(OVRInput.Axis1D.PrimaryIndexTrigger) > 0.65f;
            if (triggerDown && !_triggerLatched)
            {
                _triggerLatched = true;
                if (Time.unscaledTime - _lastTriggerDown < doubleClickWindow)
                {
                    ToggleMagicWands();                     // double trigger
                    _lastTriggerDown = -10f;
                }
                _lastTriggerDown = Time.unscaledTime;
            }
            if (!triggerDown) _triggerLatched = false;
        }

        private bool _gripLatched, _triggerLatched;
        private float _gripHoldStart = -1f;

        // ── actions ──
        private void CaptureSnapshot(bool jen)
        {
            var cam = Camera.main;
            Transform anchor = jen ? FindJenTransform() : null;

            GameObject tempGo = null;
            if (jen && anchor != null)
            {
                // frame Jen from her front, user-height, looking at her head
                Vector3 head = anchor.position + Vector3.up * 1.55f;
                Vector3 fwd = anchor.forward;
                fwd.y = 0; fwd.Normalize();
                if (fwd.sqrMagnitude < 0.01f) fwd = Vector3.forward;
                tempGo = new GameObject("snap-cam");
                var snap = tempGo.AddComponent<Camera>();
                cam = snap;
                snap.CopyFrom(Camera.main);
                tempGo.transform.SetPositionAndRotation(
                    head + fwd * 2.2f, Quaternion.LookRotation(-fwd, Vector3.up));
            }
            else if (cam == null)
            {
                FoveAI.DebugOverlay.QuestDebugOverlay.LogWarning("[Ride] no camera for snapshot");
                return;
            }

            int h = Mathf.RoundToInt(snapshotRes);
            int w = h;
            var rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32);
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            cam.targetTexture = null;
            RenderTexture.active = null;
            Destroy(rt);

            byte[] png = tex.EncodeToPNG();
            Destroy(tex);
            string kind = jen ? "jen" : "user";
            string file = Path.Combine(_snapDir, $"{kind}-{DateTime.Now:yyyyMMdd-HHmmss}.png");
            File.WriteAllBytes(file, png);
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"📸 {kind} snapshot → {file}");
            Haptic(jen ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch, 0.3f);

            if (jen && tempGo != null) Destroy(tempGo);
        }

        private Transform FindJenTransform()
        {
            // search common Jen identities; first hit wins
            GameObject jen = GameObject.Find("Jen");
            if (jen == null) jen = GameObject.Find("Jenna");
            if (jen == null) jen = GameObject.Find("Avatar");
            if (jen == null)
            {
                foreach (var anim in FindObjectsOfType<Animator>())
                {
                    if (anim.gameObject.name.Contains("Jen") || anim.gameObject.name.Contains("avatar")
                        || anim.gameObject.name.Contains("Avatar"))
                        return anim.transform;
                }
            }
            return jen != null ? jen.transform : null;
        }

        private void ToggleDebugWindow()
        {
            var overlay = FindObjectOfType<FoveAI.DebugOverlay.QuestDebugOverlay>();
            if (overlay == null)
            {
                FoveAI.DebugOverlay.QuestDebugOverlay.LogWarning("[Ride] no QuestDebugOverlay in scene");
                return;
            }
            overlay.enabled = !overlay.enabled;
            Haptic(OVRInput.Controller.LTouch, 0.4f);
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"🐞 debug window {(overlay.enabled ? "ON" : "OFF")}");
        }

        private void TogglePtt()
        {
            var vad = FindObjectOfType<FoveAI.Audio.QuestMicrophoneVAD>();
            if (vad == null)
            {
                FoveAI.DebugOverlay.QuestDebugOverlay.LogWarning("[Ride] no QuestMicrophoneVAD in scene");
                return;
            }
            vad.ToggleManualRecording();                 // B = PTT / VAD listen toggle
            Haptic(OVRInput.Controller.RTouch, 0.5f);
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"🎤 PTT/listen {(vad.IsRecordingSpeech ? "capturing" : "idle")}");
        }

        private void ToggleOvertakeSteering()
        {
            var driver = FindObjectOfType<FoveAI.Avatar.AvatarPuppetDriver>();
            if (driver == null)
            {
                FoveAI.DebugOverlay.QuestDebugOverlay.LogWarning("[Ride] no AvatarPuppetDriver — no steering to take over");
                return;
            }
            _overtakeSteering = !_overtakeSteering;
            driver.enabled = _overtakeSteering;
            Haptic(OVRInput.Controller.LTouch, 0.7f);
            Haptic(OVRInput.Controller.RTouch, 0.7f);
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"🕹️ user overtake steering: {(_overtakeSteering ? "ON — drive her" : "OFF — autonomous")}");
        }

        private void ToggleMagicWands()
        {
            if (_wands == null || _wands.Length == 0)
                _wands = FindObjectsOfType<XRHapticWand>();
            if (_wands == null || _wands.Length == 0)
            {
                FoveAI.DebugOverlay.QuestDebugOverlay.LogWarning("[Ride] no wand in scene");
                return;
            }
            foreach (var wand in _wands) wand.ToggleWandMode();
            Haptic(OVRInput.Controller.RTouch, 0.6f);
            FoveAI.DebugOverlay.QuestDebugOverlay.Log("🪄 magic wands toggled");
        }

        // ── grab / carry ──
        private void TryGrabProps()
        {
            foreach (var ctrl in new[] { OVRInput.Controller.LTouch, OVRInput.Controller.RTouch })
            {
                if (!OVRInput.Get(OVRInput.Button.PrimaryHandTrigger, ctrl)) continue;
                Transform hand = HandTransform(ctrl);
                if (hand == null) continue;

                CarriedProp existing = _carried.Find(c => c.controller == hand);
                if (existing != null) continue;

                var hit = NearestGrabbable(hand.position, grabRadius);
                if (hit == null)
                {
                    var interactable = NearestInteractableGrabbable(hand.position, grabRadius);
                    if (interactable != null)
                    {
                        interactable.enabled = true;
                        Haptic(ctrl, 0.5f);
                        var body2 = interactable.GetComponent<Rigidbody>();
                        if (body2 != null)
                        {
                            AttachProp(body2, hand);
                            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"✋ carried (interactable): {interactable.name}");
                        }
                        continue;
                    }
                    Haptic(ctrl, 0.2f, 0.08f);           // empty reach pulse
                    continue;
                }
                Haptic(ctrl, 0.6f);
                AttachProp(hit, hand);
                FoveAI.DebugOverlay.QuestDebugOverlay.Log($"✋ carrying: {hit.name}");
            }
        }

        private void AttachProp(Rigidbody body, Transform hand)
        {
            if (body == null || _carried.Exists(c => c.body == body)) return;
            var c = new CarriedProp
            {
                body = body,
                controller = hand,
                wasKinematic = body.isKinematic,
                useGravity = body.useGravity,
                localPos = hand.InverseTransformPoint(body.position),
                localRot = Quaternion.Inverse(hand.rotation) * body.rotation,
            };
            body.isKinematic = true;
            body.useGravity = false;
            _carried.Add(c);
        }

        private void ReleaseProps()
        {
            foreach (var c in _carried)
            {
                if (c.body == null) continue;
                c.body.isKinematic = c.wasKinematic;
                c.body.useGravity = c.useGravity;
                c.body.velocity = c.controller.GetComponentInParent<Rigidbody>()?.velocity ?? Vector3.zero;
            }
            _carried.Clear();
            FoveAI.DebugOverlay.QuestDebugOverlay.Log("🤚 released carry");
            Haptic(OVRInput.Controller.LTouch, 0.3f);
            Haptic(OVRInput.Controller.RTouch, 0.3f);
        }

        private Rigidbody NearestGrabbable(Vector3 pos, float radius)
        {
            Rigidbody best = null;
            float bestD = radius * radius;   // squared
            foreach (var rb in FindObjectsOfType<Rigidbody>())
            {
                if (_carried.Exists(c => c.body == rb)) continue;
                if (rb.isKinematic) continue;
                if (rb.gameObject.name.Contains("Jen") || rb.gameObject.name.Contains("Avatar")) continue;
                // only props: reasonably sized, physical objects
                var size = rb.GetComponentInChildren<Renderer>()?.bounds.size ?? Vector3.zero;
                if (size.magnitude < 0.05f || size.magnitude > 3.5f) continue;
                float d = (rb.position - pos).sqrMagnitude;
                if (d < bestD) { bestD = d; best = rb; }
            }
            return best;
        }

        private UnityEngine.XR.Interaction.Toolkit.Interactables.XRGrabInteractable NearestInteractableGrabbable(Vector3 pos, float radius)
        {
            UnityEngine.XR.Interaction.Toolkit.Interactables.XRGrabInteractable best = null;
            float bestD = radius * radius;
            foreach (var g in FindObjectsOfType<UnityEngine.XR.Interaction.Toolkit.Interactables.XRGrabInteractable>())
            {
                float d = (g.transform.position - pos).sqrMagnitude;
                if (d < bestD) { bestD = d; best = g; }
            }
            return best;
        }

        private Transform HandTransform(OVRInput.Controller ctrl)
        {
            var node = ctrl == OVRInput.Controller.LTouch ? XRNode.LeftHand : XRNode.RightHand;
            return (node == XRNode.LeftHand ? _leftHandAnchor : _rightHandAnchor);
        }

        private Transform _leftHandAnchor, _rightHandAnchor;

        private void EnsureAnchors()
        {
            if (_leftHandAnchor == null)
            {
                _leftHandAnchor = GameObject.Find("LeftHand Anchor")?.transform
                    ?? GameObject.Find("Left Controller")?.transform;
                _rightHandAnchor = GameObject.Find("RightHand Anchor")?.transform
                    ?? GameObject.Find("Right Controller")?.transform;
            }
        }

        private void LateUpdate()
        {
            if (_carried.Count == 0) return;
            foreach (var c in _carried)
            {
                if (c.body == null || c.controller == null) continue;
                c.body.position = c.controller.TransformPoint(c.localPos);
                c.body.rotation = c.controller.rotation * c.localRot;
            }
        }

        // ── haptics signal (state, not decoration) ──
        private static void Haptic(OVRInput.Controller ctrl, float strength, float dur = 0.05f)
        {
            OVRInput.SetControllerVibration(0, strength, ctrl);
        }

        private void OnEnable() => EnsureAnchors();
        private void OnDisable() => ReleaseProps();
        private void OnDestroy() => ReleaseProps();
    }
}