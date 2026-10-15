using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

/// <summary>
/// Headless scene capture, for verifying what a build actually contains without
/// putting it on a headset. Opens the scene, renders from a chosen viewpoint to a
/// PNG. This shows geometry, materials, lighting and world-space UI. It cannot
/// show XR passthrough, stereo output, or anything that only exists at runtime
/// (controller rays, WebView, live avatars loaded by VRMAvatarLoader).
///
/// Batchmode:
///   Unity -batchmode -quit -projectPath . -executeMethod RenderSceneHeadless.Render
/// Optional env:
///   RENDER_OUT      output PNG path (default: <project>/scene-render.png)
///   RENDER_W/H      pixel size (default 1600x900)
///   RENDER_CAM      comma list of camera object names, else "Main Camera"
///   RENDER_POS      x,y,z for the capture camera when no scene camera is found
/// </summary>
public static class RenderSceneHeadless
{
    public static void Render()
    {
        string scenePath = Environment.GetEnvironmentVariable("RENDER_SCENE") ?? "Assets/Scenes/FoveAI.unity";
        int width = EnvInt("RENDER_W", 1600);
        int height = EnvInt("RENDER_H", 900);
        string outPath = Environment.GetEnvironmentVariable("RENDER_OUT")
            ?? Path.Combine(Directory.GetParent(Application.dataPath).FullName, "scene-render.png");

        if (!File.Exists(scenePath))
        {
            Debug.LogError($"[RenderScene] scene missing: {scenePath}");
            EditorApplication.Exit(1);
            return;
        }

        var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
        Debug.Log($"[RenderScene] opened {scenePath} — {scene.rootCount} root objects");

        var cam = FindRequestedCamera() ?? CreateFallbackCamera();
        if (cam == null)
        {
            Debug.LogError("[RenderScene] no camera available");
            EditorApplication.Exit(1);
            return;
        }

        // RENDER_FIT=1 frames the whole scene instead of trusting the camera's own
        // transform — essential here because the passthrough camera deliberately
        // clears to transparent and sits at the XR Origin, which yields a black frame.
        if (Environment.GetEnvironmentVariable("RENDER_FIT") == "1")
        {
            var b = ComputeSceneBounds();
            if (b.size.sqrMagnitude > 0.0001f)
            {
                float dist = Mathf.Max(b.extents.magnitude * 2.2f, 0.6f);
                cam.transform.position = b.center + new Vector3(0f, b.extents.y * 0.35f, -dist);
                cam.transform.LookAt(b.center);
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.12f, 0.13f, 0.16f, 1f);
                cam.fieldOfView = 60f;
                Debug.Log($"[RenderScene] fitted to bounds center={b.center} extents={b.extents}");
            }
            else
            {
                Debug.LogWarning("[RenderScene] scene bounds are empty — nothing renderable present.");
            }
        }

        // World-space UI and canvases only lay out during a render, so make sure
        // the canvases have been through one layout pass before we capture.
        Canvas.ForceUpdateCanvases();
        UnityEditor.SceneView.RepaintAll();

        var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32)
        {
            antiAliasing = 4,
        };
        var prevTarget = cam.targetTexture;
        var prevActive = RenderTexture.active;

        cam.targetTexture = rt;
        cam.Render();
        RenderTexture.active = rt;

        var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
        tex.Apply();

        var bytes = tex.EncodeToPNG();
        Directory.CreateDirectory(Path.GetDirectoryName(outPath));
        File.WriteAllBytes(outPath, bytes);

        Debug.Log($"[RenderScene] wrote {outPath} ({bytes.Length} bytes, {width}x{height}) from '{cam.name}'");

        cam.targetTexture = prevTarget;
        RenderTexture.active = prevActive;
        rt.Release();
        UnityEngine.Object.DestroyImmediate(tex);
        UnityEngine.Object.DestroyImmediate(rt);

        EditorApplication.Exit(0);
    }

    private static Bounds ComputeSceneBounds()
    {
        var rends = UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None);
        if (rends.Length == 0) return new Bounds(Vector3.zero, Vector3.zero);

        // Ignore the tiny ray/line visuals so they don't dominate the framing.
        var has = false;
        var b = new Bounds(rends[0].bounds.center, Vector3.zero);
        foreach (var r in rends)
        {
            var size = r.bounds.size;
            if (size.x < 0.05f && size.y < 0.05f && size.z < 0.05f) continue;
            if (!has) { b = r.bounds; has = true; }
            else b.Encapsulate(r.bounds);
        }
        return has ? b : new Bounds(rends[0].bounds.center, rends[0].bounds.size);
    }

    private static Camera FindRequestedCamera()
    {
        string requested = Environment.GetEnvironmentVariable("RENDER_CAM");
        var candidates = UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsSortMode.None);
        if (candidates.Length == 0) return null;

        if (!string.IsNullOrEmpty(requested) && requested != "Main Camera")
        {
            foreach (var name in requested.Split(','))
            {
                foreach (var c in candidates)
                {
                    if (c.name.Trim().Equals(name.Trim(), StringComparison.OrdinalIgnoreCase)) return c;
                }
            }
        }
        foreach (var c in candidates)
        {
            if (c.CompareTag("MainCamera")) return c;
        }
        return candidates[0];
    }

    private static Camera CreateFallbackCamera()
    {
        string raw = Environment.GetEnvironmentVariable("RENDER_POS") ?? "0,1.6,-3";
        var parts = raw.Split(',');
        var go = new GameObject("HeadlessRenderCamera");
        var cam = go.AddComponent<Camera>();
        go.transform.position = new Vector3(
            float.Parse(parts[0]),
            float.Parse(parts[1]),
            float.Parse(parts[2]));
        cam.transform.LookAt(Vector3.zero);
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = new Color(0.06f, 0.07f, 0.09f, 1f);
        cam.fieldOfView = 60f;
        return cam;
    }

    private static int EnvInt(string key, int fallback)
    {
        return int.TryParse(Environment.GetEnvironmentVariable(key), out int v) ? v : fallback;
    }
}