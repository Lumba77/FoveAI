using UnityEngine;

namespace FoveAI.UI
{
    /// <summary>
    /// Quits the application when the button is pressed.
    /// Works on Quest 3 (closes the app) and in the Unity Editor (stops play mode).
    /// </summary>
    public class QuitButton : MonoBehaviour
    {
        public void QuitApp()
        {
            Debug.Log("[Spatial Machine] Quit button pressed — exiting application.");

#if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
#else
            Application.Quit();
#endif
        }
    }
}