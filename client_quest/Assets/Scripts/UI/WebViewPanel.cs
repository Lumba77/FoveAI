using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR;
using UnityEngine.XR.Hands;

namespace FoveAI.UI
{
    /// <summary>
    /// WebViewPanel — Renders a live Android WebView onto a floating quad in VR.
    ///
    /// Software-rendered: WebView.draw() → Bitmap → PNG → Texture2D. No plugins,
    /// no AAR — pure AndroidJavaObject calls. The WebView is attached to the
    /// Activity content view but translated far offscreen, so it gets a real
    /// layout/draw lifecycle while remaining invisible on the 2D surface.
    ///
    /// Interaction: right/left controller ray → touch (trigger), thumbstick → scroll.
    /// Non-Android platforms render a dark placeholder quad only.
    /// </summary>
    public class WebViewPanel : MonoBehaviour
    {
        [Header("Content")]
        public string url = "http://192.168.8.109:5177/chat";

        [Header("Rendering")]
        [SerializeField] private int pixelWidth = 1280;
        [SerializeField] private int pixelHeight = 800;
        [SerializeField] private float refreshInterval = 0.18f;
        [SerializeField] private Vector2 sizeMeters = new Vector2(0.80f, 0.50f);

        [Header("Interaction")]
        [SerializeField] private float triggerThreshold = 0.8f;
        [SerializeField] private float scrollSpeed = 60f;
        [SerializeField] private float rayMaxDistance = 4f;

        public string CurrentUrl { get; private set; }
        public bool IsVisible => _wantVisible && _quad != null && _quad.activeSelf;

        private Texture2D _tex;
        private MeshCollider _collider;
        private GameObject _quad;
        private bool _wantVisible = true;
        private GameObject _rightAnchor;
        private GameObject _leftAnchor;
        private InputDevice _rightDevice;
        private InputDevice _leftDevice;
        private bool _rightTouchDown;
        private bool _leftTouchDown;
        private float _rightTouchX, _rightTouchY;
        private float _leftTouchX, _leftTouchY;

        // Hand-tracking ray state (Unity XR Hands — works via OpenXR hand tracking on Quest)
        private XRHandSubsystem _handSubsystem;
        private readonly List<XRHandSubsystem> _handSubsystems = new List<XRHandSubsystem>();
        private bool _rightHandTouchDown, _leftHandTouchDown;
        private float _rightHandX, _rightHandY, _leftHandX, _leftHandY;
        private const float PinchDistanceMeters = 0.025f;

#if UNITY_ANDROID && !UNITY_EDITOR
        private AndroidJavaObject _activity;
        private AndroidJavaObject _webView;
        private AndroidJavaObject _bitmap;
        private AndroidJavaObject _canvas;
        private byte[] _pendingPng;
        private readonly object _pngLock = new object();
        private volatile bool _webReady;
#endif

        private void Start()
        {
            BuildQuad();
#if UNITY_ANDROID && !UNITY_EDITOR
            StartCoroutine(InitWebView());
#endif
        }

        private void BuildQuad()
        {
            _quad = GameObject.CreatePrimitive(PrimitiveType.Quad);
            _quad.name = "WebViewQuad";
            _quad.transform.SetParent(transform, false);
            _quad.transform.localScale = new Vector3(sizeMeters.x, sizeMeters.y, 1f);
            _collider = _quad.GetComponent<MeshCollider>();
            _quad.SetActive(_wantVisible);

            _tex = new Texture2D(pixelWidth, pixelHeight, TextureFormat.RGBA32, false);
            var fill = new Color32(10, 10, 20, 255);
            var px = new Color32[pixelWidth * pixelHeight];
            for (int i = 0; i < px.Length; i++) px[i] = fill;
            _tex.SetPixels32(px);
            _tex.Apply();

            var mat = new Material(Shader.Find("Unlit/Texture"));
            mat.mainTexture = _tex;
            _quad.GetComponent<MeshRenderer>().material = mat;
        }

        public void SetVisible(bool visible)
        {
            _wantVisible = visible;
            if (_quad != null) _quad.SetActive(visible);
        }

        public void Navigate(string target)
        {
            if (string.IsNullOrEmpty(target)) return;
            url = target;
            CurrentUrl = target;
#if UNITY_ANDROID && !UNITY_EDITOR
            if (_webReady)
            {
                _activity.Call("runOnUiThread", new AndroidJavaRunnable(() =>
                {
                    try { _webView.Call("loadUrl", target); }
                    catch (Exception e) { Debug.LogWarning($"[WebViewPanel] loadUrl failed: {e.Message}"); }
                }));
            }
#endif
        }

#if UNITY_ANDROID && !UNITY_EDITOR
        private IEnumerator InitWebView()
        {
            var upc = new AndroidJavaClass("com.unity3d.player.UnityPlayer");
            _activity = upc.GetStatic<AndroidJavaObject>("currentActivity");

            bool initDone = false;
            _activity.Call("runOnUiThread", new AndroidJavaRunnable(() =>
            {
                try
                {
                    _webView = new AndroidJavaObject("android.webkit.WebView", _activity);
                    var settings = _webView.Call<AndroidJavaObject>("getSettings");
                    settings.Call("setJavaScriptEnabled", true);
                    settings.Call("setDomStorageEnabled", true);
                    settings.Call("setMediaPlaybackRequiresUserGesture", false);
                    settings.Call("setLoadWithOverviewMode", true);
                    settings.Call("setUseWideViewPort", true);
                    _webView.Call("setWebViewClient", new AndroidJavaObject("android.webkit.WebViewClient"));
                    _webView.Call("setWebChromeClient", new AndroidJavaObject("android.webkit.WebChromeClient"));
                    // LAYER_TYPE_SOFTWARE — required for draw() into a Bitmap canvas;
                    // hardware-accelerated WebView content captures as blank.
                    _webView.Call("setLayerType", 1, null);

                    var lp = new AndroidJavaObject("android.view.ViewGroup$LayoutParams", pixelWidth, pixelHeight);
                    _activity.Call("addContentView", _webView, lp);
                    _webView.Call("setX", -8192f);
                    _webView.Call("setY", 0f);

                    var cfg = new AndroidJavaClass("android.graphics.Bitmap$Config")
                        .GetStatic<AndroidJavaObject>("ARGB_8888");
                    _bitmap = new AndroidJavaClass("android.graphics.Bitmap")
                        .CallStatic<AndroidJavaObject>("createBitmap", pixelWidth, pixelHeight, cfg);
                    _canvas = new AndroidJavaObject("android.graphics.Canvas", _bitmap);

                    _webView.Call("loadUrl", url);
                    CurrentUrl = url;
                    _webReady = true;
                    Debug.Log($"[WebViewPanel] WebView ready, loading {url}");
                }
                catch (Exception e)
                {
                    Debug.LogError($"[WebViewPanel] WebView init failed: {e.Message}");
                }
                initDone = true;
            }));

            while (!initDone) yield return null;
            StartCoroutine(CaptureLoop());
        }

        private IEnumerator CaptureLoop()
        {
            var wait = new WaitForSeconds(refreshInterval);
            while (true)
            {
                if (_webReady && IsVisible)
                {
                    _activity.Call("runOnUiThread", new AndroidJavaRunnable(CaptureFrame));
                }
                yield return wait;
                lock (_pngLock)
                {
                    if (_pendingPng != null)
                    {
                        _tex.LoadImage(_pendingPng);
                        _pendingPng = null;
                    }
                }
            }
        }

        private void CaptureFrame()
        {
            try
            {
                _webView.Call("draw", _canvas);
                var fmt = new AndroidJavaClass("android.graphics.Bitmap$CompressFormat")
                    .GetStatic<AndroidJavaObject>("PNG");
                using (var baos = new AndroidJavaObject("java.io.ByteArrayOutputStream"))
                {
                    _bitmap.Call<bool>("compress", fmt, 80, baos);
                    lock (_pngLock) { _pendingPng = baos.Call<byte[]>("toByteArray"); }
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[WebViewPanel] capture failed: {e.Message}");
            }
        }

        private void RunOnUiThread(Action action)
        {
            if (!_webReady) return;
            _activity.Call("runOnUiThread", new AndroidJavaRunnable(() =>
            {
                try { action(); }
                catch (Exception e) { Debug.LogWarning($"[WebViewPanel] ui action failed: {e.Message}"); }
            }));
        }

        private void DispatchTouch(int action, float x, float y)
        {
            RunOnUiThread(() =>
            {
                var me = new AndroidJavaClass("android.view.MotionEvent");
                long now = new AndroidJavaClass("android.os.SystemClock").CallStatic<long>("uptimeMillis");
                var ev = me.CallStatic<AndroidJavaObject>("obtain", now, now, action, x, y, 0);
                _webView.Call<bool>("dispatchTouchEvent", ev);
                ev.Call("recycle");
            });
        }

        private void ScrollBy(float dy)
        {
            RunOnUiThread(() => _webView.Call("scrollBy", 0, (int)dy));
        }
#endif

        private void Update()
        {
            PollControllerRay(true, ref _rightDevice, ref _rightAnchor, ref _rightTouchDown, ref _rightTouchX, ref _rightTouchY);
            PollControllerRay(false, ref _leftDevice, ref _leftAnchor, ref _leftTouchDown, ref _leftTouchX, ref _leftTouchY);
            PollHandRay(true, ref _rightHandTouchDown, ref _rightHandX, ref _rightHandY);
            PollHandRay(false, ref _leftHandTouchDown, ref _leftHandX, ref _leftHandY);
        }

        /// <summary>
        /// Hand-tracking ray: index proximal→tip direction, pinch (thumb↔index tip) = touch.
        /// Joint poses arrive in tracking space — converted through the controller anchors'
        /// parent (the rig transform), same convention as XRRigFixer.
        /// </summary>
        private void PollHandRay(bool right, ref bool touchDown, ref float lastX, ref float lastY)
        {
            if (_handSubsystem == null || !_handSubsystem.running)
            {
                SubsystemManager.GetSubsystems(_handSubsystems);
                _handSubsystem = _handSubsystems.Count > 0 ? _handSubsystems[0] : null;
                if (_handSubsystem == null) return;
            }

            var hand = right ? _handSubsystem.rightHand : _handSubsystem.leftHand;
            if (!hand.isTracked)
            {
                if (touchDown) { DispatchTouchSafe(1, lastX, lastY); touchDown = false; }
                return;
            }

            var prox = hand.GetJoint(XRHandJointID.IndexProximal);
            var tip = hand.GetJoint(XRHandJointID.IndexTip);
            var thumb = hand.GetJoint(XRHandJointID.ThumbTip);
            if (!prox.TryGetPose(out Pose proxPose) || !tip.TryGetPose(out Pose tipPose))
                return;

            Transform tracking = _rightAnchor != null ? _rightAnchor.transform.parent
                : (Camera.main != null ? Camera.main.transform.parent : null);
            Vector3 origin = tracking != null ? tracking.TransformPoint(tipPose.position) : tipPose.position;
            Vector3 dir = tracking != null
                ? tracking.TransformDirection(tipPose.position - proxPose.position)
                : tipPose.position - proxPose.position;
            if (dir.sqrMagnitude < 0.0001f) return;
            dir.Normalize();

            bool pinched = thumb.TryGetPose(out Pose thumbPose) &&
                Vector3.Distance(thumbPose.position, tipPose.position) < PinchDistanceMeters;

            bool hovering = false;
            float px = 0f, py = 0f;
            if (_collider != null &&
                Physics.Raycast(origin, dir, out RaycastHit hit, rayMaxDistance) &&
                hit.collider == _collider)
            {
                hovering = true;
                Vector3 local = _quad.transform.InverseTransformPoint(hit.point);
                px = Mathf.Clamp01(local.x + 0.5f) * pixelWidth;
                py = Mathf.Clamp01(0.5f - local.y) * pixelHeight;
            }

            if (hovering && pinched && !touchDown)
            {
                DispatchTouchSafe(0, px, py);
                touchDown = true;
            }
            else if (touchDown && pinched && hovering)
            {
                if (Mathf.Abs(px - lastX) > 2f || Mathf.Abs(py - lastY) > 2f)
                    DispatchTouchSafe(2, px, py);
            }
            else if (touchDown && !pinched)
            {
                DispatchTouchSafe(1, hovering ? px : lastX, hovering ? py : lastY);
                touchDown = false;
            }
            lastX = px; lastY = py;
        }

        private void PollControllerRay(bool right, ref InputDevice device, ref GameObject anchor,
            ref bool touchDown, ref float lastX, ref float lastY)
        {
            if (!IsVisible) { touchDown = false; return; }

            if (!device.isValid)
                device = InputDevices.GetDeviceAtXRNode(right ? XRNode.RightHand : XRNode.LeftHand);
            if (!device.isValid) return;

            if (anchor == null)
                anchor = GameObject.Find(right ? "RightController" : "LeftController");

            Vector3 origin, forward;
            if (anchor != null)
            {
                origin = anchor.transform.position;
                forward = anchor.transform.forward;
            }
            else
            {
                if (!device.TryGetFeatureValue(CommonUsages.devicePosition, out origin)) return;
                if (!device.TryGetFeatureValue(CommonUsages.deviceRotation, out var rot)) return;
                forward = rot * Vector3.forward;
            }

            bool hovering = false;
            float px = 0f, py = 0f;
            if (_collider != null &&
                Physics.Raycast(origin, forward, out RaycastHit hit, rayMaxDistance) &&
                hit.collider == _collider)
            {
                hovering = true;
                // Quad mesh spans -0.5..0.5 in local space; map hit to UV
                Vector3 local = _quad.transform.InverseTransformPoint(hit.point);
                px = Mathf.Clamp01(local.x + 0.5f) * pixelWidth;
                py = Mathf.Clamp01(0.5f - local.y) * pixelHeight;
            }

            device.TryGetFeatureValue(CommonUsages.trigger, out float trigger);
            bool pressed = trigger >= triggerThreshold;

            if (hovering && pressed && !touchDown)
            {
                DispatchTouchSafe(0, px, py); // ACTION_DOWN
                touchDown = true;
            }
            else if (touchDown && pressed && hovering)
            {
                if (Mathf.Abs(px - lastX) > 2f || Mathf.Abs(py - lastY) > 2f)
                    DispatchTouchSafe(2, px, py); // ACTION_MOVE
            }
            else if (touchDown && !pressed)
            {
                DispatchTouchSafe(1, hovering ? px : lastX, hovering ? py : lastY); // ACTION_UP
                touchDown = false;
            }
            lastX = px; lastY = py;

            if (hovering && device.TryGetFeatureValue(CommonUsages.primary2DAxis, out Vector2 stick))
            {
                if (Mathf.Abs(stick.y) > 0.3f) ScrollBySafe(-stick.y * scrollSpeed * Time.deltaTime);
            }
        }

        private void DispatchTouchSafe(int action, float x, float y)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            DispatchTouch(action, x, y);
#endif
        }

        private void ScrollBySafe(float dy)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            ScrollBy(dy);
#endif
        }

        private void OnDestroy()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (_webReady)
            {
                _activity.Call("runOnUiThread", new AndroidJavaRunnable(() =>
                {
                    try
                    {
                        var parent = _webView.Call<AndroidJavaObject>("getParent");
                        if (parent != null) parent.Call("removeView", _webView);
                        _webView.Call("destroy");
                    }
                    catch { }
                }));
            }
            _bitmap?.Call("recycle");
#endif
        }
    }
}
