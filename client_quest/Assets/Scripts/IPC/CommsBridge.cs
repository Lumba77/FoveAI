using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace FoveAI.Comms
{
    /// <summary>
    /// CommsBridge — Ported from Frontend/XR_Vessel/src/senses/CommsBridge.ts
    /// Lets Alice handle the user's email, SMS, phone calls, and WhatsApp messages
    /// via the FoveAI backend REST API (/api/comms/*).
    ///
    /// Voice: Can answer calls for the user (with consent) using VoiceClone.
    /// SMS: Read / respond to text messages via phone bridge.
    /// Email: Read / write email via Gmail API or IMAP.
    /// WhatsApp: Send messages via linked phone.
    /// </summary>
    public class CommsBridge : MonoBehaviour
    {
        [Header("Backend")]
        public string baseUrl = "http://192.168.8.100:8402";
        public string apiPath = "/api/comms";
        public float timeoutSeconds = 10f;

        [Header("Status (Read-only)")]
        public bool lastRequestOk;
        public string lastError;

        private string Api => $"{baseUrl}{apiPath}";

        private async void Awake()
        {
            // Resolve backend URL from shared config (serverIp + XRLF httpPort) if available
            if (FoveAI.Config.ConfigLoader.Settings == null)
                await FoveAI.Config.ConfigLoader.LoadConfigAsync();
            var s = FoveAI.Config.ConfigLoader.Settings;
            if (s != null)
                baseUrl = $"http://{s.serverIp}:{s.httpPort}";
        }

        // ── Data Models ──

        [System.Serializable]
        public struct Email
        {
            public string id;
            public string from;
            public string subject;
            public string snippet;
            public string body;
            public string date;
        }

        [System.Serializable]
        public struct SmsMessage
        {
            public string from;
            public string body;
            public long timestamp;
            public bool read;
        }

        [System.Serializable]
        public struct CallInfo
        {
            public string number;
            public string name;
            public long timestamp;
            public float duration;
            public bool missed;
        }

        // ── EMAIL ──

        public void ListEmails(int maxResults = 10, Action<Email[]> onComplete = null)
        {
            StartCoroutine(GetRequest($"{Api}/email/list?max={maxResults}",
                json =>
                {
                    if (string.IsNullOrEmpty(json)) { onComplete?.Invoke(Array.Empty<Email>()); return; }
                    var wrapper = JsonUtility.FromJson<EmailListWrapper>("{\"emails\":" + json + "}");
                    onComplete?.Invoke(wrapper.emails ?? Array.Empty<Email>());
                },
                () => onComplete?.Invoke(Array.Empty<Email>())));
        }

        public void SendEmail(string to, string subject, string body, Action<bool> onComplete = null)
        {
            var payload = new SendEmailPayload { to = to, subject = subject, body = body };
            string json = JsonUtility.ToJson(payload);
            StartCoroutine(PostRequest($"{Api}/email/send", json,
                ok => { if (ok) Log($"Email sent to {to}"); onComplete?.Invoke(ok); }));
        }

        public void ReadEmail(string id, Action<string> onComplete = null)
        {
            StartCoroutine(GetRequest($"{Api}/email/read?id={UnityWebRequest.EscapeURL(id)}",
                json =>
                {
                    if (string.IsNullOrEmpty(json)) { onComplete?.Invoke(null); return; }
                    try
                    {
                        var wrapper = JsonUtility.FromJson<EmailBodyWrapper>("{\"body\":" + json + "}");
                        onComplete?.Invoke(wrapper.body);
                    }
                    catch { onComplete?.Invoke(null); }
                },
                () => onComplete?.Invoke(null)));
        }

        // ── SMS ──

        public void ListSms(int maxResults = 10, Action<SmsMessage[]> onComplete = null)
        {
            StartCoroutine(GetRequest($"{Api}/sms/list?max={maxResults}",
                json =>
                {
                    if (string.IsNullOrEmpty(json)) { onComplete?.Invoke(Array.Empty<SmsMessage>()); return; }
                    var wrapper = JsonUtility.FromJson<SmsListWrapper>("{\"messages\":" + json + "}");
                    onComplete?.Invoke(wrapper.messages ?? Array.Empty<SmsMessage>());
                },
                () => onComplete?.Invoke(Array.Empty<SmsMessage>())));
        }

        public void SendSms(string to, string body, Action<bool> onComplete = null)
        {
            var payload = new SendSmsPayload { to = to, body = body };
            string json = JsonUtility.ToJson(payload);
            StartCoroutine(PostRequest($"{Api}/sms/send", json,
                ok => { if (ok) Log($"SMS sent to {to}"); onComplete?.Invoke(ok); }));
        }

        // ── CALLS ──

        public void GetRecentCalls(Action<CallInfo[]> onComplete = null)
        {
            StartCoroutine(GetRequest($"{Api}/calls/recent",
                json =>
                {
                    if (string.IsNullOrEmpty(json)) { onComplete?.Invoke(Array.Empty<CallInfo>()); return; }
                    var wrapper = JsonUtility.FromJson<CallListWrapper>("{\"calls\":" + json + "}");
                    onComplete?.Invoke(wrapper.calls ?? Array.Empty<CallInfo>());
                },
                () => onComplete?.Invoke(Array.Empty<CallInfo>())));
        }

        /// <summary>Answer a call and speak as the user (uses VoiceClone for TTS).</summary>
        public void AnswerCall(string callId, string greeting, bool useUserVoice = true, Action<bool> onComplete = null)
        {
            var payload = new AnswerCallPayload { callId = callId, greeting = greeting, useUserVoice = useUserVoice };
            string json = JsonUtility.ToJson(payload);
            StartCoroutine(PostRequest($"{Api}/calls/answer", json,
                ok => { if (ok) Log("Answered call as user"); onComplete?.Invoke(ok); }));
        }

        // ── WHATSAPP ──

        public void SendWhatsApp(string to, string body, Action<bool> onComplete = null)
        {
            var payload = new SendSmsPayload { to = to, body = body };
            string json = JsonUtility.ToJson(payload);
            StartCoroutine(PostRequest($"{Api}/whatsapp/send", json, onComplete));
        }

        // ── Context for LLM ──

        public string GetContext()
        {
            return "[COMMS BRIDGE] Email (read/send), SMS, calls, WhatsApp available. " +
                   "Can answer phone as user (voice cloned).";
        }

        // ── HTTP Helpers ──

        private IEnumerator GetRequest(string url, Action<string> onSuccess, Action onFailure)
        {
            lastError = null;
            using var req = UnityWebRequest.Get(url);
            req.timeout = Mathf.RoundToInt(timeoutSeconds);
            req.SetRequestHeader("Accept", "application/json");
            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                lastRequestOk = true;
                // Extract the inner JSON array/object from the response
                string json = req.downloadHandler.text;
                // Try to unwrap {"emails": [...]}, {"messages": [...]}, {"calls": [...]}, {"body": "..."}
                onSuccess?.Invoke(ExtractInnerJson(json));
            }
            else
            {
                lastRequestOk = false;
                lastError = req.error;
                Log($"GET failed: {req.error}");
                onFailure?.Invoke();
            }
        }

        private IEnumerator PostRequest(string url, string jsonBody, Action<bool> onComplete)
        {
            lastError = null;
            using var req = new UnityWebRequest(url, "POST");
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(jsonBody));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            req.timeout = Mathf.RoundToInt(timeoutSeconds);
            yield return req.SendWebRequest();

            bool ok = req.result == UnityWebRequest.Result.Success;
            lastRequestOk = ok;
            if (!ok) { lastError = req.error; Log($"POST failed: {req.error}"); }
            onComplete?.Invoke(ok);
        }

        /// <summary>
        /// Extracts the inner JSON value from a wrapper like {"emails": [...]} or {"body": "..."}.
        /// If the response is already a bare array/object, returns it as-is.
        /// </summary>
        private string ExtractInnerJson(string json)
        {
            if (string.IsNullOrEmpty(json)) return null;
            json = json.Trim();
            if (json.StartsWith("{") && json.EndsWith("}"))
            {
                // Look for known wrapper keys
                string[] keys = { "emails", "messages", "calls", "body" };
                foreach (var key in keys)
                {
                    string search = "\"" + key + "\":";
                    int idx = json.IndexOf(search, StringComparison.OrdinalIgnoreCase);
                    if (idx >= 0)
                    {
                        int valueStart = idx + search.Length;
                        // Skip whitespace
                        while (valueStart < json.Length && char.IsWhiteSpace(json[valueStart])) valueStart++;
                        if (valueStart >= json.Length) continue;

                        // If value is a string (starts with "), extract the string
                        if (json[valueStart] == '"')
                        {
                            int end = json.IndexOf('"', valueStart + 1);
                            if (end > valueStart)
                                return json.Substring(valueStart, end - valueStart + 1);
                        }
                        // If value is an array or object, find the matching bracket
                        else if (json[valueStart] == '[' || json[valueStart] == '{')
                        {
                            char open = json[valueStart];
                            char close = open == '[' ? ']' : '}';
                            int depth = 0;
                            for (int i = valueStart; i < json.Length; i++)
                            {
                                if (json[i] == open) depth++;
                                else if (json[i] == close)
                                {
                                    depth--;
                                    if (depth == 0) return json.Substring(valueStart, i - valueStart + 1);
                                }
                            }
                        }
                    }
                }
            }
            return json;
        }

        private void Log(string msg)
        {
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[Comms] {msg}");
        }

        // ── JSON Wrappers (Unity JsonUtility needs wrapper classes) ──

        [System.Serializable]
        private class EmailListWrapper { public Email[] emails; }

        [System.Serializable]
        private class SmsListWrapper { public SmsMessage[] messages; }

        [System.Serializable]
        private class CallListWrapper { public CallInfo[] calls; }

        [System.Serializable]
        private class EmailBodyWrapper { public string body; }

        [System.Serializable]
        private class SendEmailPayload { public string to; public string subject; public string body; }

        [System.Serializable]
        private class SendSmsPayload { public string to; public string body; }

        [System.Serializable]
        private class AnswerCallPayload { public string callId; public string greeting; public bool useUserVoice; }
    }
}
