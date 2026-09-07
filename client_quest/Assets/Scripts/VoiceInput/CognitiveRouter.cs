using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using UnityEngine;
using FoveAI.Avatar;

namespace Lumax.Quest3Bridge
{
    /// <summary>
    /// Self-Puppeteering Bracket Parser - Unity port of XR_Vessel's BracketParser.ts
    /// ================================================================================
    ///
    /// This is the "nerve centre of self-puppeteering." Every bracket token the LLM
    /// emits passes through here FIRST, before TTS or UI display. Tokens are parsed,
    /// stripped from the spoken text, and dispatched to the AvatarAnimationBrain.
    ///
    /// This REPLACES the old simple bracket parser that only understood:
    ///   [GESTURE: "name"], [EMOTION: "name"], [WALK: distance]
    ///
    /// The new self-puppeteering vocabulary (from MindCore VR_BODY_CONTROL_TOKENS):
    ///
    ///   <emotion:happy>              - Facial expression + body language posture
    ///   <emotion:happy intensity=0.7>- With intensity parameter
    ///   <micro:nod>                  - Quick procedural head/body movement
    ///   <micro:tilt>                 - Head tilt (curiosity, warmth)
    ///   <micro:shake>                - Head shake (disagreement)
    ///   <micro:look_away>            - Glance aside (shyness, thinking)
    ///   <micro:double_take>          - Quick look-away-and-back (surprise)
    ///   <micro:bow>                  - Small bow (gratitude, greeting)
    ///   <movement:walk_forward 2m>   - Walk forward N meters
    ///   <movement:move_to x=0 y=0 z=1> - Walk to specific coordinates
    ///   <movement:sit>               - Transition to sitting posture
    ///   <movement:lay_down>          - Lie down
    ///   <movement:stand_up>          - Return to standing
    ///   <movement:kneel>             - Kneel down
    ///   <movement:steer_on>          - Enable user manual steering
    ///   <movement:steer_off>         - Return to autonomous control
    ///   <movement:move_stop>         - Stop all movement
    ///   <mode:coexist>               - Silent warm presence
    ///   <mode:cowork>                - Co-working mode
    ///   <mode:coop>                  - Active co-operation
    ///   <mode:rest>                  - Resting/evening mode
    ///   <mode:follow>                - Follow the user
    ///   <mode:intimate>              - Close companion mode
    ///   <animation:Name>             - Direct animation clip trigger
    ///
    /// Also strips internal monologue blocks before TTS:
    ///   Qwen/DeepSeek think blocks, compagent thought blocks, and (thought: ...) parens
    ///
    /// Ported from: frontend/XR_Vessel/src/senses/BracketParser.ts
    /// </summary>
    public class CognitiveRouter : MonoBehaviour
    {
        [Tooltip("The avatar root that contains the Animator and VRM Blendshape proxy")]
        public GameObject AvatarRoot;

        private FoveAI.IPC.FoveAIWebSocketClient _wsClient;
        private Lumax.Quest3Bridge.Quest3TTSClient _ttsClient;
        private FoveAI.Avatar.AvatarAnimationBrain _brain;
        private FoveAI.Avatar.VRMAAnimationLoader _vrmaLoader;
        private FoveAI.Avatar.AvatarBlendshapeDriver _blendshapeDriver;
        private FoveAI.Avatar.AvatarPuppetDriver _puppetDriver;

        // ── Regex: Typed bracket tokens ──
        // Matches: <emotion:happy>, <movement:walk_forward 2m>, <mode:coexist>, etc.
        private static readonly Regex BracketRegex = new Regex(
            @"<(audio|emotion|micro|flavour|request|dev|action|movement|mode|code|animation|gesture):([^>]+)>",
            RegexOptions.IgnoreCase | RegexOptions.Compiled);

        // ── Regex: Think blocks (internal monologue - stripped before TTS) ──
        // Pattern built via concat to avoid editor tag-stripping issues.
        // Matches both standard <think>...</think> and Qwen/DeepSeek variants.
        private static readonly string ThinkOpen = "<" + "think" + ">";
        private static readonly string ThinkClose = "</" + "think" + ">";
        private static readonly Regex ThinkRegex = new Regex(
            ThinkOpen + @"[\s\S]*?" + ThinkClose,
            RegexOptions.IgnoreCase | RegexOptions.Compiled);
        private static readonly Regex ThoughtRegex = new Regex(
            @"<thought>[\s\S]*?</thought>",
            RegexOptions.IgnoreCase | RegexOptions.Compiled);

        // ── Regex: Parenthetical tokens ──
        // (emotion: happy) -> <emotion:happy>  — typed parens convert to bracket form
        // (thought: ...) -> stripped entirely — internal monologue, never spoken
        private static readonly Regex ParenThoughtRegex = new Regex(
            @"\(\s*thought\s*:.*?\)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
        private static readonly Regex ParenRegex = new Regex(
            @"\((emotion|action|gesture|movement|micro|mode):\s*([^)]+)\)",
            RegexOptions.IgnoreCase | RegexOptions.Compiled);

        // ── Regex: Simple bracket fallback (no type prefix) ──
        // Matches <sigh_content>, <happy>, etc. — but NOT closing tags like </think>
        private static readonly Regex SimpleBracketRegex = new Regex(
            @"<(?!/)([a-z][a-z0-9_]+)>", RegexOptions.Compiled);

        // ── Known emotion keywords (for simple bracket fallback) ──
        private static readonly HashSet<string> EmotionKeywords = new HashSet<string>
        {
            "happy", "sad", "surprised", "curious", "content", "neutral", "angry", "fearful",
            "thinking", "relaxed", "excited", "confused", "worried", "proud", "embarrassed",
            "grateful", "hopeful", "lonely", "nostalgic", "peaceful", "playful", "shy",
            "affectionate", "calm", "tired", "sleepy", "love", "joy", "fun",
            "concerned", "grateful"
        };

        // ── HTML tags to preserve (not strip as bracket tokens) ──
        private static readonly HashSet<string> HtmlTags = new HashSet<string>
        {
            "div", "span", "p", "br", "b", "i", "em", "a", "img", "script", "style",
            "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
            "table", "tr", "td", "th", "meta", "link", "head", "body", "html",
            "input", "form", "button", "svg", "path", "circle", "rect", "line", "text"
        };

        // ── Known movement commands ──
        private static readonly HashSet<string> MovementCommands = new HashSet<string>
        {
            "walk_forward", "move_to", "steer", "steer_on", "steer_off", "stop", "move_stop",
            "sit", "stand_up", "lay_down", "kneel", "interact"
        };

        // ── Known social modes ──
        private static readonly HashSet<string> ModeCommands = new HashSet<string>
        {
            "coexist", "cowork", "coop", "rest", "follow", "intimate"
        };

        // ── Gesture name → VRMA clip mapping (for micro-gestures) ──
        private static readonly Dictionary<string, string> GestureClipMap =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                { "nod", "vrma_02" },
                { "tilt", "vrma_05" },
                { "shake", "vrma_06" },
                { "look_away", "lookaround" },
                { "lookaround", "lookaround" },
                { "double_take", "surprised" },
                { "bow", "vrma_03" },
                { "wave", "goodbye" },
                { "waving", "goodbye" },
                { "clap", "clapping" },
                { "clapping", "clapping" },
                { "think", "thinking" },
                { "thinking", "thinking" },
                { "shrug", "vrma_07" },
                { "dance", "vrma_01" },
                { "jump", "jump" },
                { "relax", "relax" },
                { "sleepy", "sleepy" },
                { "blush", "blush" },
            };

        private void Start()
        {
            _wsClient = FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            _ttsClient = FindAnyObjectByType<Lumax.Quest3Bridge.Quest3TTSClient>();

            RefreshAvatarReferences();

            if (_wsClient != null)
            {
                _wsClient.OnChatTextReceived += InterceptAndRoute;
            }
            else
            {
                Debug.LogWarning("[CognitiveRouter] No WebSocket client found — bracket parsing inactive");
            }
        }

        public void SetAvatarRoot(GameObject avatarRoot)
        {
            AvatarRoot = avatarRoot;
            RefreshAvatarReferences();
        }

        private void RefreshAvatarReferences()
        {
            if (AvatarRoot == null) return;
            _brain = AvatarRoot.GetComponentInChildren<FoveAI.Avatar.AvatarAnimationBrain>();
            _vrmaLoader = AvatarRoot.GetComponentInChildren<FoveAI.Avatar.VRMAAnimationLoader>();
            _blendshapeDriver = AvatarRoot.GetComponentInChildren<FoveAI.Avatar.AvatarBlendshapeDriver>();
            _puppetDriver = AvatarRoot.GetComponentInChildren<FoveAI.Avatar.AvatarPuppetDriver>();
        }

        private void OnDisable()
        {
            if (_wsClient != null)
            {
                _wsClient.OnChatTextReceived -= InterceptAndRoute;
            }
        }

        // ════════════════════════════════════════════════════════════════
        // MAIN PARSER - Self-Puppeteering Gateway
        // ════════════════════════════════════════════════════════════════

        private void InterceptAndRoute(string responseText)
        {
            if (string.IsNullOrWhiteSpace(responseText)) return;

            string text = responseText;

            try
            {
                // ── Step 1: Strip think blocks and thought blocks ──
                // These are internal monologue - NEVER spoken by TTS
                text = ThinkRegex.Replace(text, "");
                text = ThoughtRegex.Replace(text, "");

                // ── Step 2: Strip parenthetical thoughts (thought: ...) ──
                // The soul prompt instructs the model to write (thought: ...)
                // These must be stripped before TTS, NOT converted to bracket tokens
                text = ParenThoughtRegex.Replace(text, "");

                // ── Step 3: Convert typed parenthetical tokens to bracket form ──
                // (emotion: happy) -> <emotion:happy>
                text = ParenRegex.Replace(text, m => "<" + m.Groups[1].Value + ":" + m.Groups[2].Value + ">");

                // ── Step 4: Parse and strip typed bracket tokens ──
                string primaryEmotion = null;
                text = BracketRegex.Replace(text, m =>
                {
                    string type = m.Groups[1].Value.ToLowerInvariant();
                    string tagContent = m.Groups[2].Value.Trim();
                    string fullMatch = m.Value;

                    // Parse tag name + params
                    string[] parts = tagContent.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                    string tagName = parts.Length > 0 ? parts[0] : tagContent;

                    var parameters = new Dictionary<string, string>();
                    for (int i = 1; i < parts.Length; i++)
                    {
                        int eqIdx = parts[i].IndexOf('=');
                        if (eqIdx > 0)
                        {
                            string key = parts[i].Substring(0, eqIdx);
                            string val = parts[i].Substring(eqIdx + 1);
                            parameters[key] = val;
                        }
                    }

                    // Route based on type — all dispatchers are null-safe
                    switch (type)
                    {
                        case "emotion":
                            float intensity = ParseFloat(parameters, "intensity", "weight", 1.0f);
                            DispatchEmotion(tagName, intensity);
                            primaryEmotion = tagName;
                            break;

                        case "micro":
                            DispatchMicroGesture(tagName, parameters);
                            break;

                        case "movement":
                            DispatchMovement(tagName, parts, parameters, fullMatch);
                            break;

                        case "action":
                            // action:sit -> movement type
                            if (MovementCommands.Contains(tagName))
                                DispatchMovement(tagName, parts, parameters, fullMatch);
                            else
                                DispatchAnimation(tagName, parameters);
                            break;

                        case "mode":
                            if (ModeCommands.Contains(tagName))
                                DispatchSocialMode(tagName);
                            break;

                        case "animation":
                        case "gesture":
                            DispatchAnimation(tagName, parameters);
                            break;

                        case "audio":
                            Debug.Log("[CognitiveRouter] Audio token (soundboard not yet wired): <audio:" + tagName + ">");
                            break;

                        default:
                            Debug.Log("[CognitiveRouter] Unhandled token type: " + type + ":" + tagName);
                            break;
                    }

                    return ""; // Strip the token from spoken text
                });

                // ── Step 5: Parse simple bracket fallback ──
                // e.g. <happy>, <sigh_content> - no type prefix
                text = SimpleBracketRegex.Replace(text, m =>
                {
                    string tagContent = m.Groups[1].Value;

                    // Skip HTML tags
                    if (HtmlTags.Contains(tagContent))
                        return m.Value;

                    // Emotion keyword -> dispatch as emotion
                    if (EmotionKeywords.Contains(tagContent))
                    {
                        DispatchEmotion(tagContent, 1.0f);
                        primaryEmotion = tagContent;
                        return "";
                    }

                    // Otherwise treat as audio/soundboard token (not yet wired in Unity)
                    Debug.Log("[CognitiveRouter] Simple bracket (soundboard): <" + tagContent + ">");
                    return "";
                });

                // ── Step 6: Clean up whitespace and send to TTS ──
                text = Regex.Replace(text, @"\s+", " ").Trim();

                if (_ttsClient != null && !string.IsNullOrWhiteSpace(text))
                {
                    _ttsClient.Speak(text);
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[CognitiveRouter] Parse error (non-fatal): {ex.Message}");
                // Fallback: speak the raw text without parsing
                if (_ttsClient != null && !string.IsNullOrWhiteSpace(responseText))
                {
                    _ttsClient.Speak(responseText);
                }
            }
        }

        // ════════════════════════════════════════════════════════════════
        // DISPATCHERS - Route parsed tokens to the AvatarAnimationBrain
        // All dispatchers are null-safe — they log a warning if the target
        // component is missing rather than crashing.
        // ════════════════════════════════════════════════════════════════

        private void DispatchEmotion(string emotion, float intensity)
        {
            if (_brain != null)
            {
                _brain.ApplyEmotionState(emotion, intensity);
            }
            else if (_blendshapeDriver != null)
            {
                _blendshapeDriver.ApplyEmotion(emotion, intensity);
            }
            else
            {
                Debug.LogWarning($"[CognitiveRouter] <emotion:{emotion}> — no brain or blendshape driver");
            }
        }

        private void DispatchMicroGesture(string gesture, Dictionary<string, string> parameters)
        {
            if (_brain != null)
            {
                _brain.QueueMicroGesture(gesture);
            }
            else if (_vrmaLoader != null)
            {
                // Fallback: play the mapped VRMA clip directly
                string clipName = MapGestureToClip(gesture);
                if (!string.IsNullOrEmpty(clipName))
                    _vrmaLoader.CrossFade(clipName, 0.3f);
            }
            else
            {
                Debug.LogWarning($"[CognitiveRouter] <micro:{gesture}> — no brain or VRMA loader");
            }
        }

        private void DispatchMovement(string command, string[] parts,
            Dictionary<string, string> parameters, string fullMatch)
        {
            switch (command)
            {
                case "walk_forward":
                    float meters = ParseFloat(parameters, "meters", "distance", -1f);
                    if (meters < 0)
                    {
                        // Try to extract from the raw token content
                        string raw = fullMatch.Replace("<movement:walk_forward", "").Replace(">", "").Trim();
                        var numMatch = Regex.Match(raw, @"(\d+(?:\.\d+)?)");
                        meters = numMatch.Success ? ParseInvariantFloat(numMatch.Groups[1].Value) : 1f;
                    }
                    if (_brain != null)
                        _brain.WalkForward(meters);
                    else if (_puppetDriver != null)
                        _puppetDriver.HandleMotorAction("walk_forward", $"{{\"distance\":{meters}}}");
                    else
                        Debug.LogWarning("[CognitiveRouter] walk_forward — no brain or puppet driver");
                    break;

                case "move_to":
                    float x = ParseFloat(parameters, "x", "", 0f);
                    float y = ParseFloat(parameters, "y", "", 0f);
                    float z = ParseFloat(parameters, "z", "", 0f);
                    if (_brain != null)
                        _brain.CommandMoveTo(new Vector3(x, y, z));
                    else
                        Debug.LogWarning("[CognitiveRouter] move_to — no brain");
                    break;

                case "sit":
                    if (_vrmaLoader != null)
                        _vrmaLoader.CrossFade("waiting", 0.5f); // closest to sitting posture
                    if (_brain != null)
                        _brain.SetConversationState(FoveAI.Avatar.AvatarAnimationBrain.ConversationState.Idle);
                    Debug.Log("[CognitiveRouter] <movement:sit> — posture transition");
                    break;

                case "stand_up":
                    if (_vrmaLoader != null)
                        _vrmaLoader.CrossFade("relax", 0.5f); // return to standing idle
                    if (_brain != null)
                        _brain.SetConversationState(FoveAI.Avatar.AvatarAnimationBrain.ConversationState.Idle);
                    Debug.Log("[CognitiveRouter] <movement:stand_up> — posture transition");
                    break;

                case "lay_down":
                    if (_vrmaLoader != null)
                        _vrmaLoader.CrossFade("sleepy", 1f);
                    if (_brain != null)
                        _brain.drives.energy = 0.2f;
                    Debug.Log("[CognitiveRouter] <movement:lay_down> — posture transition");
                    break;

                case "kneel":
                    // No dedicated kneel animation — use waiting as closest posture
                    if (_vrmaLoader != null)
                        _vrmaLoader.CrossFade("waiting", 0.5f);
                    Debug.Log("[CognitiveRouter] <movement:kneel> — posture transition (using waiting)");
                    break;

                case "steer_on":
                case "steer_off":
                case "steer":
                    bool enabled = command == "steer_on" ||
                        (command == "steer" && ParseBool(parameters, "enabled", false));
                    Debug.Log("[CognitiveRouter] <movement:" + command + "> — steering " + enabled);
                    // Steering is handled by AvatarPuppetDriver's double-grip detection
                    // We log it; the user enables it physically
                    break;

                case "stop":
                case "move_stop":
                    if (_brain != null)
                    {
                        _brain.SetConversationState(FoveAI.Avatar.AvatarAnimationBrain.ConversationState.Idle);
                        _brain.CommandReturnHome();
                    }
                    Debug.Log("[CognitiveRouter] <movement:stop> — returning to idle");
                    break;

                default:
                    Debug.LogWarning("[CognitiveRouter] Unknown movement command: " + command);
                    break;
            }
        }

        private void DispatchSocialMode(string mode)
        {
            if (_brain == null)
            {
                Debug.LogWarning($"[CognitiveRouter] <mode:{mode}> — no brain");
                return;
            }

            // Map social modes to brain behavior adjustments
            switch (mode)
            {
                case "coexist":
                    _brain.drives.socialNeed = 0.8f;
                    _brain.drives.expressiveness = 0.1f;
                    break;

                case "cowork":
                    _brain.drives.socialNeed = 0.6f;
                    _brain.drives.expressiveness = 0.3f;
                    _brain.drives.curiosity = 0.7f;
                    break;

                case "coop":
                    _brain.drives.socialNeed = 0.5f;
                    _brain.drives.expressiveness = 0.7f;
                    _brain.drives.curiosity = 0.8f;
                    break;

                case "rest":
                    _brain.drives.energy = 0.3f;
                    _brain.drives.expressiveness = 0.2f;
                    if (_vrmaLoader != null) _vrmaLoader.CrossFade("sleepy", 1f);
                    break;

                case "follow":
                    _brain.drives.socialNeed = 0.9f;
                    _brain.drives.restlessness = 0.3f;
                    break;

                case "intimate":
                    _brain.drives.socialNeed = 0.95f;
                    _brain.drives.expressiveness = 0.5f;
                    _brain.drives.curiosity = 1.0f;
                    break;
            }

            Debug.Log($"[CognitiveRouter] <mode:{mode}> → brain drives updated");
        }

        private void DispatchAnimation(string name, Dictionary<string, string> parameters)
        {
            if (_brain != null)
            {
                _brain.PlayGesture(name);
            }
            else if (_vrmaLoader != null)
            {
                _vrmaLoader.CrossFade(name, 0.5f);
            }
            else
            {
                Debug.LogWarning($"[CognitiveRouter] <animation:{name}> — no brain or VRMA loader");
            }
        }

        // ════════════════════════════════════════════════════════════════
        // HELPERS
        // ════════════════════════════════════════════════════════════════

        private static string MapGestureToClip(string gesture)
        {
            if (GestureClipMap.TryGetValue(gesture, out var clip))
                return clip;
            return gesture; // pass through — PlayAnimation will handle unknown names
        }

        private static float ParseFloat(Dictionary<string, string> p, string key1, string key2, float def)
        {
            if (p != null)
            {
                string v;
                if (p.TryGetValue(key1, out v))
                {
                    float f = TryParseFloat(v);
                    if (!float.IsNaN(f)) return f;
                }
                if (!string.IsNullOrEmpty(key2) && p.TryGetValue(key2, out v))
                {
                    float f = TryParseFloat(v);
                    if (!float.IsNaN(f)) return f;
                }
            }
            return def;
        }

        /// <summary>
        /// Culture-invariant float parse. The Quest may use a non-US locale
        /// where decimal separator is comma — float.Parse("0.7") crashes there.
        /// </summary>
        private static float TryParseFloat(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) return float.NaN;
            s = s.Trim().Trim('"', '\'');
            // Replace comma with dot for locales that use comma decimals
            s = s.Replace(',', '.');
            if (float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out float f))
                return f;
            return float.NaN;
        }

        private static float ParseInvariantFloat(string s)
        {
            float f = TryParseFloat(s);
            return float.IsNaN(f) ? 0f : f;
        }

        private static bool ParseBool(Dictionary<string, string> p, string key, bool def)
        {
            string v;
            if (p != null && p.TryGetValue(key, out v))
            {
                return v.Equals("true", StringComparison.OrdinalIgnoreCase) || v == "1";
            }
            return def;
        }
    }
}
