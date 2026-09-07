using UnityEngine;

namespace FoveAI.UI
{
    /// <summary>
    /// Toggles the chat panel visibility when the user presses the X button
    /// on the left Quest 3 XR controller. When shown, the panel is positioned
    /// 2m in front of the user's head (camera) at eye level.
    ///
    /// The avatar is always visible at start; the chat panel starts hidden.
    /// </summary>
    public class XRPanelToggle : MonoBehaviour
    {
        [Header("References")]
        [Tooltip("The chat canvas panel to toggle (hidden at start).")]
        [SerializeField] private GameObject chatPanel;

        [Tooltip("The XR camera (Main Camera) used to position the panel in front of the user.")]
        [SerializeField] private Camera xrCamera;

        [Header("Panel Positioning")]
        [Tooltip("Distance in front of the user to place the panel (meters).")]
        [SerializeField] private float spawnDistance = 2f;

        [Tooltip("Height offset relative to the camera (meters). 0 = eye level.")]
        [SerializeField] private float heightOffset = 0f;

        [Tooltip("If true, the panel follows the user's gaze direction. If false, panel stays at a fixed world position after spawn.")]
        [SerializeField] private bool followGaze = false;

        [Header("Input")]
        [Tooltip("Key used in Desktop mode to toggle the panel (e.g. Tab). Only used with Legacy Input Manager.")]
#pragma warning disable CS0414
        [SerializeField] private KeyCode desktopToggleKey = KeyCode.Tab;
#pragma warning restore CS0414

        private bool _panelVisible;

        private void Awake()
        {
            // Find camera if not assigned
            if (xrCamera == null)
            {
                xrCamera = Camera.main;
                if (xrCamera == null)
                {
                    xrCamera = FindAnyObjectByType<Camera>();
                }
            }

            // Hide panel at start
            if (chatPanel != null)
            {
                _panelVisible = chatPanel.activeSelf;
            }
            else
            {
                Debug.LogError("[XRPanelToggle] No chatPanel assigned!");
            }
        }

        private void Update()
        {
            bool xButtonPressed = false;

#if ENABLE_INPUT_SYSTEM
            // --- Input System package ---

            // Desktop fallback: Tab key
            var keyboard = UnityEngine.InputSystem.Keyboard.current;
            if (keyboard != null)
            {
                if (keyboard.tabKey.wasPressedThisFrame)
                {
                    xButtonPressed = true;
                }
            }

            // Quest 3 controllers: check gamepad buttons
            // On Quest 3, the X button on the left controller maps to buttonNorth
            var gamepad = UnityEngine.InputSystem.Gamepad.current;
            if (gamepad != null)
            {
                if (gamepad.buttonNorth.wasPressedThisFrame)
                {
                    xButtonPressed = true;
                }
            }

            // Meta XR Core SDK fallback (most reliable for Quest)
            try
            {
                if (OVRInput.GetDown(OVRInput.RawButton.Start))
                {
                    xButtonPressed = true;
                }
            }
            catch { }

#elif ENABLE_LEGACY_INPUT_MANAGER
            // --- Legacy Input Manager ---

            // Quest 3 X button (left controller) = joystick button 2
            if (Input.GetKeyDown(KeyCode.JoystickButton2))
            {
                xButtonPressed = true;
            }

            // Desktop fallback
            if (Input.GetKeyDown(desktopToggleKey))
            {
                xButtonPressed = true;
            }

            // Also check common XR input mappings
            try
            {
                if (Input.GetButtonDown("X Button"))
                {
                    xButtonPressed = true;
                }
            }
            catch
            {
                // "X Button" axis not configured — ignore
            }
#endif

            if (xButtonPressed)
            {
                TogglePanel();
            }

            // If panel is visible and followGaze is true, update position each frame
            if (_panelVisible && followGaze && chatPanel != null && xrCamera != null)
            {
                PositionPanelInFrontOfUser();
            }
        }

        /// <summary>
        /// Toggle the chat panel visibility. When showing, position it 2m in front of the user.
        /// </summary>
        public void TogglePanel()
        {
            if (chatPanel == null) return;

            _panelVisible = !_panelVisible;
            chatPanel.SetActive(_panelVisible);

            if (_panelVisible)
            {
                PositionPanelInFrontOfUser();
                Debug.Log("[XRPanelToggle] Panel shown — positioned 2m in front of user.");
            }
            else
            {
                Debug.Log("[XRPanelToggle] Panel hidden.");
            }
        }

        /// <summary>
        /// Position the chat panel 2m in front of the user's camera, at eye level.
        /// </summary>
        private void PositionPanelInFrontOfUser()
        {
            if (xrCamera == null || chatPanel == null) return;

            Vector3 cameraPos = xrCamera.transform.position;
            Vector3 cameraForward = xrCamera.transform.forward;
            cameraForward.y = 0f; // keep panel at same height, ignore pitch
            cameraForward.Normalize();

            // Position 2m in front of the camera
            Vector3 panelPos = cameraPos + cameraForward * spawnDistance;
            panelPos.y = cameraPos.y + heightOffset;

            chatPanel.transform.position = panelPos;

            // Face the panel toward the user
            Vector3 lookDir = (cameraPos - panelPos).normalized;
            lookDir.y = 0f;
            if (lookDir.sqrMagnitude > 0.001f)
            {
                chatPanel.transform.rotation = Quaternion.LookRotation(lookDir, Vector3.up);
            }
        }

        /// <summary>
        /// Show the panel (called from external scripts or UI buttons).
        /// </summary>
        public void ShowPanel()
        {
            if (chatPanel == null) return;
            _panelVisible = true;
            chatPanel.SetActive(true);
            PositionPanelInFrontOfUser();
        }

        /// <summary>
        /// Hide the panel (called from external scripts or UI buttons).
        /// </summary>
        public void HidePanel()
        {
            if (chatPanel == null) return;
            _panelVisible = false;
            chatPanel.SetActive(false);
        }
    }
}