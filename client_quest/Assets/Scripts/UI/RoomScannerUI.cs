using System.Collections;
using UnityEngine;
using UnityEngine.UI;

namespace FoveAI.UI
{
    public class RoomScannerUI : MonoBehaviour
    {
        private GameObject _uiCanvas;
        private Text _statusText;

        private void Awake()
        {
            CreateCanvas();
        }

        private void CreateCanvas()
        {
            _uiCanvas = new GameObject("RoomScannerCanvas");
            _uiCanvas.transform.SetParent(this.transform, false);
            
            // Position it 1.5m in front of the user
            _uiCanvas.transform.localPosition = new Vector3(0, 1.5f, 1.5f);
            
            Canvas canvas = _uiCanvas.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            _uiCanvas.GetComponent<RectTransform>().sizeDelta = new Vector2(400, 100);
            _uiCanvas.transform.localScale = Vector3.one * 0.002f;

            var scaler = _uiCanvas.AddComponent<CanvasScaler>();
            scaler.dynamicPixelsPerUnit = 100;

            GameObject textObj = new GameObject("StatusText");
            textObj.transform.SetParent(_uiCanvas.transform, false);
            _statusText = textObj.AddComponent<Text>();
            
            // Standard Arial font
            _statusText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            _statusText.color = new Color(1f, 0.8f, 0.2f, 1.0f); // Amber
            _statusText.fontSize = 32;
            _statusText.alignment = TextAnchor.MiddleCenter;
            _statusText.text = "Scanning physical environment...";
            
            RectTransform textRect = textObj.GetComponent<RectTransform>();
            textRect.sizeDelta = new Vector2(400, 100);
            textRect.localPosition = Vector3.zero;
        }

        public void ShowSuccessAndFade()
        {
            if (_statusText != null)
            {
                _statusText.color = new Color(0.2f, 1.0f, 0.2f, 1.0f); // Green
                _statusText.text = "Environment Mapped!";
                StartCoroutine(FadeOutRoutine());
            }
        }

        private IEnumerator FadeOutRoutine()
        {
            yield return new WaitForSeconds(2.0f);
            
            float duration = 1.0f;
            float elapsed = 0f;
            Color startColor = _statusText.color;
            
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float alpha = Mathf.Lerp(1f, 0f, elapsed / duration);
                _statusText.color = new Color(startColor.r, startColor.g, startColor.b, alpha);
                yield return null;
            }
            
            Destroy(_uiCanvas);
        }
    }
}
