using UnityEngine;
using FoveAI.IPC;
using System.Collections;

// =============================================================================
//  AvatarIKController  -  Alicechan head/gaze + hand IK
//
//  Uses Unity built-in OnAnimatorIK() — works on ANY Humanoid rig without
//  requiring the Animations.Rigging package, which can silently fail on Quest.
//
//  Gaze priority:
//   1. If backend sends motor.ik_target for head -> track that point
//   2. Otherwise -> smoothly look at Camera.main (the user's headset)
//
//  Hand IK: TwoBoneIK via OnAnimatorIK goal overrides.
// =============================================================================

public class AvatarIKController : MonoBehaviour
{
    [Header("IK Settings")]
    [SerializeField] private float gazeSpeed   = 4.0f;
    [SerializeField] private float gazeWeight  = 0.7f; // body weight for look-at
    [SerializeField] private float headWeight  = 1.0f;
    [SerializeField] private float eyesWeight  = 0.9f;
    [SerializeField] private float clampWeight = 0.4f; // limits extreme angles

    [Header("Breathing")]
    [SerializeField] private float breathAmplitude = 0.005f; // subtle spine bob
    [SerializeField] private float breathRate      = 0.25f;  // cycles per second

    // -- IK state from backend --
    private Vector3  _headTargetWorld;
    private bool     _backendControllingHead = false;
    private Vector3  _rightHandTarget;
    private Vector3  _leftHandTarget;
    private bool     _rightHandActive = false;
    private bool     _leftHandActive  = false;

    // -- Smoothed look-at --
    private Vector3  _smoothGazeTarget;
    private Animator _anim;
    private Transform _spineBone;
    private Transform _headBone;
    private Transform _neckBone;
    private float    _breathPhase = 0f;

    [System.Serializable] private class WsMsg    { public string event_type; public string payload; }
    [System.Serializable] private class IKPayload{ public string limb; public float x, y, z; public bool active; }

    // =========================================================================
    //  Lifecycle
    // =========================================================================
    private void Start()
    {
        _anim = GetComponentInChildren<Animator>();
        if (_anim == null)
            Debug.LogError("[AvatarIK] No Animator found. Gaze IK will not work.");

        // Cache bones for procedural manipulation
        if (_anim != null && _anim.isHuman)
        {
            _spineBone = _anim.GetBoneTransform(HumanBodyBones.Spine);
            _headBone  = _anim.GetBoneTransform(HumanBodyBones.Head);
            _neckBone  = _anim.GetBoneTransform(HumanBodyBones.Neck);
        }

        // Default gaze target = 2m in front at eye height
        _smoothGazeTarget = transform.position + transform.forward * 2f + Vector3.up * 1.5f;

        // Subscribe to WebSocket events
        StartCoroutine(SubscribeWhenReady());
    }

    private IEnumerator SubscribeWhenReady()
    {
        FoveAIWebSocketClient ws = null;
        float timeout = 10f;
        while (ws == null && timeout > 0f)
        {
            ws = FindAnyObjectByType<FoveAIWebSocketClient>();
            yield return new WaitForSeconds(0.5f);
            timeout -= 0.5f;
        }
        if (ws != null)
            ws.OnRawMessageReceived += HandleWsMessage;
        else
            Debug.LogWarning("[AvatarIK] FoveAIWebSocketClient not found within 10s. Running in fallback gaze mode.");
    }

    private void OnDestroy()
    {
        var ws = FindAnyObjectByType<FoveAIWebSocketClient>();
        if (ws != null) ws.OnRawMessageReceived -= HandleWsMessage;
    }

    // =========================================================================
    //  LateUpdate — procedural breathing and gaze (replaces OnAnimatorIK)
    // =========================================================================
    private void LateUpdate()
    {
        // 1. Procedural Breathing (Spine Bob)
        if (_spineBone != null)
        {
            _breathPhase += breathRate * Time.deltaTime * Mathf.PI * 2f;
            float bob = Mathf.Sin(_breathPhase) * breathAmplitude;

            Vector3 localPos = _spineBone.localPosition;
            localPos.y += bob;
            _spineBone.localPosition = localPos;
        }

        // 2. Procedural Gaze (LookAt)
        if (_headBone != null && _neckBone != null)
        {
            Vector3 gazeGoal;
            if (_backendControllingHead)
            {
                gazeGoal = _headTargetWorld;
            }
            else if (Camera.main != null)
            {
                // Track user's headset
                gazeGoal = Camera.main.transform.position;
            }
            else
            {
                gazeGoal = transform.position + transform.forward * 2f + Vector3.up * 1.5f;
            }

            // Smooth the target so gaze doesn't snap
            _smoothGazeTarget = Vector3.Lerp(_smoothGazeTarget, gazeGoal, Time.deltaTime * gazeSpeed);

            // Calculate rotation towards target with strict angle clamping
            Vector3 lookDir = (_smoothGazeTarget - _headBone.position).normalized;
            if (lookDir.sqrMagnitude > 0.001f)
            {
                // Clamp horizontal and vertical gaze angle to max 40 degrees from avatar forward
                float angle = Vector3.Angle(transform.forward, lookDir);
                if (angle > 40f)
                {
                    lookDir = Vector3.RotateTowards(transform.forward, lookDir, Mathf.Deg2Rad * 40f, 0f);
                }

                Quaternion targetRot = Quaternion.LookRotation(lookDir, transform.up);
                
                // Subtle, gentle blend on neck and head so neck never over-twists
                _neckBone.rotation = Quaternion.Slerp(_neckBone.rotation, targetRot, headWeight * 0.25f);
                _headBone.rotation = Quaternion.Slerp(_headBone.rotation, targetRot, headWeight * 0.65f);
            }
        }

        // Note: Procedural Hand IK (TwoBoneIK) is omitted here since it requires a solver.
        // If VRM 1.0 hands need IK, they should use a dedicated IK component (like FastIK)
        // or a dummy AnimatorController to re-enable OnAnimatorIK.
    }

    // =========================================================================
    //  WebSocket message handler
    // =========================================================================
    private void HandleWsMessage(string raw)
    {
        if (!raw.Contains("motor.ik_target")) return;
        try
        {
            var msg = JsonUtility.FromJson<WsMsg>(raw);
            if (msg.event_type != "motor.ik_target") return;

            var payload = JsonUtility.FromJson<IKPayload>(msg.payload);
            var pt = new Vector3(payload.x, payload.y, payload.z);

            switch (payload.limb)
            {
                case "head":
                    _headTargetWorld        = pt;
                    _backendControllingHead = payload.active;
                    break;
                case "right_hand":
                    _rightHandTarget  = pt;
                    _rightHandActive  = payload.active;
                    break;
                case "left_hand":
                    _leftHandTarget = pt;
                    _leftHandActive = payload.active;
                    break;
            }
        }
        catch { }
    }
}
