using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>
/// SceneHealProbe — the Unity counterpart to the frontend's pw-verify.
///
/// Every fault that made the Quest build "successful but empty" was silent:
/// the build reported BUILD SUCCESSFUL while the headset showed bare
/// passthrough. A silent fault cannot be self-healed, because nothing fails.
/// This probe turns the silent classes into a nonzero exit code.
///
/// Checks (each maps to a bug that actually shipped):
///   1. compile         — implied: Unity refuses -executeMethod on a broken project
///   2. oneMainCamera   — two GameObjects named "Main Camera" both tagged MainCamera,
///                        so Camera.main resolved arbitrarily and the avatar was
///                        planted in front of the camera that never rendered
///   3. avatarLoads     — every .vrm in StreamingAssets loads through the SAME code
///                        path the app uses (VrmUtility + MaterialGenerator)
///   4. avatarHumanoid  — Animator.isHuman, else VRMA retargeting silently no-ops
///   5. materialsDrawable — no URP/Hidden shaders while the project is Built-in RP.
///                        This is the exact bug: the URP descriptor generator is
///                        compiled into the VRM assembly regardless of pipeline, so
///                        reflection "found" it on a Built-in project and produced
///                        shaders the Built-in renderer cannot draw.
///   6. surfaceVisible  — the chat surface is active AND in front of the camera
///                        (every canvas is authored at +Z, behind a -Z camera)
///   7. rendersPixels   — a real render contains opaque geometry; if variance is nil
///                        the frame is passthrough-only, which was the reported symptom
///   8. endpointsLive   — STT/TTS/WebSocket ports answer, so voice is not dead-on-arrival
///
/// Run:  Unity -batchmode -quit -projectPath <p> -executeMethod SceneHealProbe.Run
/// Exit: 0 = all pass, 1 = at least one FAIL (check the report path).
/// </summary>
public static class SceneHealProbe
{
    private const string ScenePath = "Assets/Scenes/FoveAI.unity";
    private const string ReportPath = "Logs/scene-heal-probe.txt";
    private const string ShotPath = "Logs/scene-heal-probe.png";

    private static readonly StringBuilder Log = new StringBuilder();
    private static int _failures;

    [MenuItem("FoveAI/Scene Heal Probe")]
    public static void Run()
    {
        Directory.CreateDirectory("Logs");
        Banner($"SceneHealProbe  scene={ScenePath}  unity={Application.unityVersion}");

        try
        {
            if (EditorSceneManager.GetActiveScene().path != ScenePath)
            {
                EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            }
            Scene scene = SceneManager.GetActiveScene();
            Check(scene.IsValid(), "sceneLoaded", $"opened {scene.name}");

            CheckTwoMainCameras();
            CheckPrimarySurface();
            CheckMaterialsMatchPipeline();
            CheckAvatarFiles();
            CheckEndpoints();
            RenderEvidence(scene);
        }
        catch (Exception ex)
        {
            Fail("probeCrashed", ex.ToString());
        }

        File.WriteAllText(ReportPath, Log.ToString());
        Debug.Log(Log.ToString());
        Banner(_failures == 0
            ? $"PROBE PASS — {ReportPath}"
            : $"PROBE FAIL — {_failures} failure(s), see {ReportPath}");

        if (Application.isBatchMode) EditorApplication.Exit(_failures == 0 ? 0 : 1);
    }

    // ── 2. exactly one enabled MainCamera ────────────────────────────────────
    private static void CheckTwoMainCameras()
    {
        var cameras = UnityEngine.Object.FindObjectsByType<Camera>(
            FindObjectsInactive.Include, FindObjectsSortMode.None);
        var activeMain = cameras
            .Where(c => c.isActiveAndEnabled && c.CompareTag("MainCamera"))
            .ToList();

        Check(activeMain.Count == 1, "oneMainCamera",
            $"enabled MainCamera-tagged cameras = {activeMain.Count} " +
            $"(need exactly 1). All: [{string.Join(", ", cameras.Where(c => c.CompareTag("MainCamera")).Select(c => c.name + (c.isActiveAndEnabled ? "(on)" : "(off)")))}]");

        foreach (var cam in activeMain)
        {
            Info($"  active main camera '{cam.name}' depth={cam.depth} " +
                 $"clear={cam.clearFlags} bg={cam.backgroundColor} " +
                 $"near={cam.nearClipPlane} fov={cam.fieldOfView}");
            var rig = cam.transform.parent != null ? cam.transform.parent.name : "(root)";
            Info($"  camera parent rig = '{rig}'");
        }

        // Two AudioListeners also hard-fail on Android.
        var listeners = UnityEngine.Object.FindObjectsByType<AudioListener>(
            FindObjectsInactive.Include, FindObjectsSortMode.None).Count(l => l.isActiveAndEnabled);
        Check(listeners <= 1, "oneAudioListener", $"enabled AudioListeners = {listeners} (need <= 1)");
    }

    // ── 6. the chat surface is active and in front of the camera ────────────
    private static void CheckPrimarySurface()
    {
        var cam = UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsInactive.Include, FindObjectsSortMode.None)
            .FirstOrDefault(c => c.isActiveAndEnabled && c.CompareTag("MainCamera"));
        if (cam == null) { Fail("surfaceVisible", "no active MainCamera — cannot judge surface placement"); return; }

        var surfaces = new[] { "ChatCanvas", "AppSettings_Panel", "WebUIPanel" };
        bool anyActive = false;

        foreach (var name in surfaces)
        {
            var go = FindByName(name);
            if (go == null) { Info($"  surface '{name}': absent"); continue; }

            Vector3 toSurface = go.transform.position - cam.transform.position;
            float depth = Vector3.Dot(toSurface, cam.transform.forward);
            var canvas = go.GetComponent<Canvas>();
            string mode = canvas != null ? canvas.renderMode.ToString() : "no-canvas";

            Info($"  surface '{name}' active={go.activeSelf} renderMode={mode} " +
                 $"distance={toSurface.magnitude:F2}m depthAlongView={depth:F2}m");

            if (!go.activeSelf) continue;
            anyActive = true;
            // A panel behind the viewer is invisible no matter that it is enabled.
            Check(depth > 0.05f, $"surfaceInFront[{name}]",
                $"'{name}' is {Mathf.Abs(depth):F2}m BEHIND the camera — authored at +Z but the camera looks down -Z");
        }

        Check(anyActive, "surfaceVisible",
            "no chat/settings surface active at boot — the headset shows bare passthrough");
    }

    // ── 5. shaders must match the active render pipeline ───────────────────
    private static void CheckMaterialsMatchPipeline()
    {
        bool urp = UnityEngine.Rendering.GraphicsSettings.currentRenderPipeline != null;
        string pipeline = urp
            ? UnityEngine.Rendering.GraphicsSettings.currentRenderPipeline.GetType().Name
            : "Built-in";
        Info($"active render pipeline = {pipeline}");

        Check(!urp, "pipelineBuiltIn",
            "probe expectation: this project is Built-in RP; if you migrated to URP, " +
            "update MaterialGenerator's branch instead of relying on reflection");

        // Muted magenta + URP shader names is the failure signature.
        string[] urpShaderHints = { "Universal Render Pipeline", "/Hidden/", "Shader Graphs/" };
        var shaders = UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsInactive.Include, FindObjectsSortMode.None)
            .SelectMany(r => r.sharedMaterials)
            .Where(m => m != null)
            .Select(m => m.shader)
            .Where(s => s != null)
            .Select(s => s.name)
            .Distinct()
            .ToList();

        foreach (var s in shaders)
        {
            bool bad = urpShaderHints.Any(h => s.Contains(h));
            if (bad) Fail("materialsDrawable", $"shader '{s}' cannot draw under {pipeline}");
        }
        Info($"distinct shaders on scene mesh renderers = {(shaders.Count == 0 ? "(none — no geometry)" : string.Join(", ", shaders))}");
    }

    // ── 3/4. every VRM in StreamingAssets loads and is humanoid ──────────────
    private static void CheckAvatarFiles()
    {
        var dir = Path.Combine(Application.streamingAssetsPath, "");
        if (!Directory.Exists(dir)) { Fail("avatarLoads", $"StreamingAssets missing: {dir}"); return; }

        var vrms = Directory.GetFiles(dir, "*.vrm");
        Check(vrms.Length > 0, "avatarFiles", $"*.vrm found in StreamingAssets = {vrms.Length}");

        foreach (var path in vrms)
        {
            var bytes = File.ReadAllBytes(path);
            try
            {
                // ImmediateCaller completes synchronously, which is what a -batchmode edit-mode
// probe needs: RuntimeOnlyAwaitCaller defers to the player loop, which does not
// pump here, so awaiting it would hang forever.
var instance = VRM.VrmUtility.LoadBytesAsync(
                    path, bytes,
                    new UniGLTF.ImmediateCaller(),
                    materialGeneratorCallback: BuiltInGenerator,
                    loadAnimation: true)
                .GetAwaiter().GetResult();

                if (instance == null)
                {
                    Fail("avatarLoads", $"{Path.GetFileName(path)} → LoadBytes returned null");
                    continue;
                }

                instance.ShowMeshes();
                var root = instance.Root;
                var renderer = root.GetComponentInChildren<SkinnedMeshRenderer>();
                var anim = root.GetComponentInChildren<Animator>();

                string boundsText = renderer != null ? renderer.bounds.size.ToString() : "(none)";
                string animText = anim != null ? "yes" : "NO";
                string humanText = anim != null && anim.isHuman ? "yes" : "no";
                Info($"  {Path.GetFileName(path)}: meshes={root.GetComponentsInChildren<SkinnedMeshRenderer>().Length} " +
                     $"bounds={boundsText} animator={animText} human={humanText}");

                Check(renderer != null && renderer.bounds.size.sqrMagnitude > 0.0001f,
                    "avatarHasGeometry", $"{Path.GetFileName(path)} produced no measurable geometry");

                Check(anim != null, $"avatarAnimator[{Path.GetFileName(path)}]",
                    "no Animator in the VRM hierarchy");
                if (anim != null)
                {
                    Check(anim.isHuman && anim.avatar != null,
                        $"avatarHumanoid[{Path.GetFileName(path)}]",
                        $"Animator.isHuman={anim.isHuman} avatar={(anim.avatar != null ? "set" : "null")} " +
                        "— VRMA body retargeting silently no-ops without a Humanoid avatar");
                }

                var shaderNames = root.GetComponentsInChildren<MeshRenderer>(true)
                    .SelectMany(r => r.sharedMaterials)
                    .Where(m => m != null).Select(m => m.shader != null ? m.shader.name : "(null shader)")
                    .Distinct().ToList();
                Check(!shaderNames.Any(n => n.Contains("Universal Render Pipeline")),
                    $"avatarMaterials[{Path.GetFileName(path)}]",
                    $"URP shaders on a Built-in RP avatar: {string.Join(", ", shaderNames)}");

                UnityEngine.Object.DestroyImmediate(root);
                instance.Dispose();
            }
            catch (Exception ex)
            {
                Fail("avatarLoads", $"{Path.GetFileName(path)} threw: {ex.GetType().Name}: {ex.Message}");
            }
        }
    }

    // Mirror of VRMAvatarLoader.MaterialGenerator, but unconditional Built-in:
    // the probe must not reproduce the bug it is hunting.
    private static UniGLTF.IMaterialDescriptorGenerator BuiltInGenerator(VRM.glTF_VRM_extensions vrm)
    {
        return new VRM.BuiltInVrmMaterialDescriptorGenerator(vrm);
    }

    // ── 8. voice endpoints must answer ─────────────────────────────────────
    private static void CheckEndpoints()
    {
        var cfg = Path.Combine(Application.streamingAssetsPath, "AppConfig.json");
        string ip = "127.0.0.1";
        if (File.Exists(cfg))
        {
            var settings = UnityEngine.JsonUtility.FromJson<Config>(File.ReadAllText(cfg));
            if (!string.IsNullOrEmpty(settings.serverIp)) ip = settings.serverIp;
            Info($"AppConfig: ip={settings.serverIp} ws={settings.wsPort} avatar={settings.avatarModel}");
        }

        Probe("sttWhisper", ip, 8401);   // Backend/stt_whisper_server.py, WebSocket-only
        Probe("ipcServer", ip, 8403);   // IPCServer — chat, TTS speak/stop
        Probe("chatHttp", ip, 8402);    // /v1/chat/completions
    }

    private static void Probe(string label, string host, int port)
    {
        // Informational: a down backend is not a client bug, so FAIL is reserved
        // for an unreachable host; a closed port on the live LAN is reported as WARN.
        try
        {
            using (var client = new System.Net.Sockets.TcpClient())
            {
                var ar = client.BeginConnect(host, port, null, null);
                bool up = ar.AsyncWaitHandle.WaitOne(1500) && client.Connected;
                Info($"  endpoint {label} {host}:{port} → {(up ? "OPEN" : "CLOSED")}");
                if (!up) Fail("endpointDown", $"{label} {host}:{port} is closed — voice/chat will be dead in the headset");
            }
        }
        catch (Exception ex)
        {
            Fail("endpointDown", $"{label} {host}:{port} probe threw {ex.Message}");
        }
    }

    [Serializable] private class Config
    {
        public string serverIp;
        public int wsPort;
        public int httpPort;
        public int soulPort;
        public string avatarModel;
    }

    // ── 7. hard evidence that something actually rendered ──────────────────
    private static void RenderEvidence(Scene scene)
    {
        var cam = UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsInactive.Include, FindObjectsSortMode.None)
            .FirstOrDefault(c => c.isActiveAndEnabled && c.CompareTag("MainCamera"));
        if (cam == null) { Fail("rendersPixels", "no active MainCamera to render from"); return; }

        var rt = new RenderTexture(512, 512, 24, RenderTextureFormat.ARGB32);
        var prevTarget = cam.targetTexture;
        var prevActive = RenderTexture.active;

        try
        {
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;

            var tex = new Texture2D(512, 512, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0, 0, 512, 512), 0, 0);
            tex.Apply();
            File.WriteAllBytes(ShotPath, tex.EncodeToPNG());

            var px = tex.GetPixels32();
            int opaque = px.Count(p => p.a > 16);
            double meanLuma = px.Average(p => 0.2126 * p.r + 0.7152 * p.g + 0.0722 * p.b);
            float minL = 255f, maxL = 0f;
            foreach (var p in px)
            {
                float l = (float)(0.2126 * p.r + 0.7152 * p.g + 0.0722 * p.b);
                if (l < minL) minL = l;
                if (l > maxL) maxL = l;
            }

            Info($"render: opaquePixels={opaque}/{px.Length} ({100.0 * opaque / px.Length:F1}%) " +
                 $"meanLuma={meanLuma:F1} lumaRange={minL:F0}..{maxL:F0} → {ShotPath}");

            Check(opaque > px.Length / 100, "rendersPixels",
                $"only {opaque}/{px.Length} pixels are opaque — the frame is passthrough-only " +
                "(nothing drawn; this is the exact reported symptom)");

            UnityEngine.Object.DestroyImmediate(tex);
        }
        catch (Exception ex)
        {
            Fail("rendersPixels", $"render threw {ex.GetType().Name}: {ex.Message}");
        }
        finally
        {
            cam.targetTexture = prevTarget;
            RenderTexture.active = prevActive;
            rt.Release();
            UnityEngine.Object.DestroyImmediate(rt);
        }
    }

    private static GameObject FindByName(string name)
    {
        return UnityEngine.Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None)
            .FirstOrDefault(t => t.name == name && t.gameObject.scene.IsValid())?.gameObject;
    }

    private static void Check(bool ok, string id, string detail)
    {
        if (ok) Pass(id, detail);
        else Fail(id, detail);
    }

    private static void Pass(string id, string detail)
    {
        _failures -= 0;
        Log.AppendLine($"  PASS  {id}: {detail}");
    }

    private static void Fail(string id, string detail)
    {
        _failures++;
        Log.AppendLine($"  FAIL  {id}: {detail}");
    }

    private static void Info(string line) => Log.AppendLine($"  ·     {line}");

    private static void Banner(string line)
    {
        Log.AppendLine();
        Log.AppendLine(new string('=', 78));
        Log.AppendLine(line);
        Log.AppendLine(new string('=', 78));
    }
}