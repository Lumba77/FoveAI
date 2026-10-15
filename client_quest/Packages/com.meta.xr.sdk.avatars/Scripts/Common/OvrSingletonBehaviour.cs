/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * Licensed under the Oculus SDK License Agreement (the "License");
 * you may not use the Oculus SDK except in compliance with the License,
 * which is provided at the time of installation or download, or which
 * otherwise accompanies this software in either electronic or hard copy form.
 *
 * You may obtain a copy of the License at
 *
 * https://developer.oculus.com/licenses/oculussdk/
 *
 * Unless required by applicable law or agreed to in writing, the Oculus SDK
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


#nullable disable

using UnityEngine;

namespace Oculus.Avatar2
{
    public class OvrSingletonBehaviour<T> : MonoBehaviour where T : OvrSingletonBehaviour<T>
    {
        public static string TypeName => typeNameCache_ ??= typeof(T).Name;

        private static string typeNameCache_ = null;

        private static string logScope => TypeName;

        public static bool hasInstance => !shuttingDown && Instance != null && !Instance._willShutdown;

        // Get the currently created Singleton instance, neither creates nor finds instances
        public static T Instance { get; private set; } = null;

        public static bool shuttingDown { get; private set; } = false;

        // If this Singleton is not instantiated, create it - try to fix Instantiation order instead
        public static void EnsureInstantiated() { if (Instance is null) { Instantiate(); } }

        // Should be called only once per Singleton Type, before it is used
        public static void Instantiate()
        {
            if (hasInstance)
            {
                OvrAvatarLog.LogError($"Instantiate called when singleton of {TypeName} already exists"
                    , logScope, Instance);
            }
            else if (initializing)
            {
                OvrAvatarLog.LogError(
                    $"Instantiate called when singleton of {TypeName} is already initializing"
                    , logScope, Instance);
            }
            else if (shuttingDown)
            {
                OvrAvatarLog.LogError($"Instantiate called when singleton of {TypeName} is already shutting down"
                    , logScope, Instance);
            }

            Debug.Assert(!hasInstance && !initializing && !shuttingDown);

            if (!initializing && !hasInstance)
            {
                // Search for existing instance. Do not assign to _instance, as it may not have Awoken yet
#if UNITY_6000_0_OR_NEWER
                var sceneInstance = FindAnyObjectByType<T>();
#else // ^^^ UNITY_6000_0_OR_NEWER / !UNITY_6000_0_OR_NEWER vvv
                var sceneInstance = FindObjectOfType<T>();
#endif // !UNITY_6000_0_OR_NEWER

                // Create new instance if one doesn't already exist.
                if (sceneInstance == null || sceneInstance._willShutdown)
                {
                    if (!shuttingDown)
                    {
                        // Need to create a new GameObject to attach the singleton to.
                        var singletonObject = new GameObject(typeof(T) + " (Singleton)", typeof(T));
                        OvrAvatarLog.LogDebug($"Singleton instance not found in scene, created {singletonObject.name}."
                            , logScope, singletonObject);

                        singletonObject.GetComponent<T>().CheckStartup();
                    }
                    else
                    {
                        OvrAvatarLog.LogError(
                            $"Singleton '{TypeName}' attempted spawn during shutdown. Ignoring."
                            , logScope, sceneInstance);
                    }
                }
                else if (!sceneInstance._hasStarted)
                {
                    if (sceneInstance.enabled && sceneInstance.gameObject.activeInHierarchy)
                    {
                        sceneInstance.ExecuteStartup();
                    }
                    else
                    {
                        OvrAvatarLog.LogError(
                            $"Singleton '{TypeName}' is in scene ('{sceneInstance.gameObject.name}') but disabled, no instance created."
                            , logScope, sceneInstance);
                    }
                }
                else
                {
                    OvrAvatarLog.LogWarning(
                        $"Singleton `{TypeName}` was started before Instantiate!"
                        , logScope, sceneInstance);
                }
            }
        }

        // Subclasses may implement custom startup logic in `Initialize`
        protected virtual void Initialize() { }
        // Subclasses may implement custom shutdown logic in `Shutdown`
        protected virtual void Shutdown() { }

        // Derived singleton classes can not reliably implement Awake
        protected void Awake() => CheckStartup();

        // Derived classes can not reliably implement Awake or Start,
        // but we don't have anything to do in Start and implementing it will add overhead at runtime
        // TODO: Better way to accomplish this goal
#if UNITY_EDITOR
        protected void Start() { }
#endif

        protected void OnApplicationQuit() => CheckShutdown(false);
        protected void OnDestroy() => CheckShutdown(true);

        // For error detection

        private static bool initializing = false;
        protected bool IsSingletonInstance => Instance == this;
        private bool _hasStarted = false;
        private bool _willShutdown = false;
        private bool _hasShutdown = false;

        private void CheckStartup()
        {
            Debug.Assert(!initializing);

            // May have been jump started by `Instance` access
            if (_hasStarted) { return; }

            if (Instance == null)
            {
                ExecuteStartup();
            }
            else
            {
                OvrAvatarLog.LogWarning($"Duplicate `{TypeName}` instance created on {gameObject.name}, destroying", logScope);
                Destroy(this);
            }
        }
        private void CheckShutdown(bool isDestroy)
        {
            _willShutdown = true;
            if (!_hasStarted || _hasShutdown) { return; }

            Debug.Assert(Instance == this || Instance is null);
            if (Instance == this)
            {
                ExecuteShutdown(isDestroy);
            }
        }

        private void ExecuteStartup()
        {
            initializing = true;
            try
            {
                Initialize();

#if UNITY_EDITOR
                UnityEditor.EditorApplication.quitting += EmergencyShutdown;
                UnityEditor.AssemblyReloadEvents.beforeAssemblyReload += EmergencyShutdown;

                if (Application.isPlaying)
#endif
                {
                    // `DontDestroyOnLoad` requires root parent
                    if (transform.parent == null)
                    {
                        OvrAvatarLog.LogVerbose("Marking DontDestroyOnLoad on singleton"
                            , logScope, this);

                        OvrSingletonBehaviour<T>.DontDestroyOnLoad(this);
                    }
                    else
                    {
                        OvrAvatarLog.LogInfo("Root gameObject required for DontDestroyOnLoad call"
                            , logScope, this);
                    }
                }
                Instance = (T)this;

                _hasStarted = true;
            }
            catch (System.Exception e)
            {
                OvrAvatarLog.LogException("initialize", e, logScope, this);
            }
            initializing = false;
        }

        private void ExecuteShutdown(bool isDestroy)
        {
            shuttingDown = true;
            try
            {
                Shutdown();
            }
            catch (System.Exception e)
            {
                OvrAvatarLog.LogException("shutdown", e, logScope, this);
            }

            Instance = null;
            _hasShutdown = true;

#if UNITY_EDITOR
            UnityEditor.EditorApplication.quitting -= EmergencyShutdown;
            UnityEditor.AssemblyReloadEvents.beforeAssemblyReload -= EmergencyShutdown;
#endif

            if (!isDestroy && this != null)
            {
#if UNITY_EDITOR
                if (!Application.isPlaying)
                {
                    // Don't want to destroy prefabs, only scene instances
                    if (!UnityEditor.PrefabUtility.IsPartOfAnyPrefab(this))
                    {
                        // Can't call Destroy from edit mode
                        OvrSingletonBehaviour<T>.DestroyImmediate(this);
                    }
                }
                else
#endif
                {
                    OvrSingletonBehaviour<T>.Destroy(this);
                }
            }

            shuttingDown = false;
        }

#if UNITY_EDITOR
        // Used for editor close and assembly reload
        // Simply removes the `isDestroy` param to match those event signatures
        private void EmergencyShutdown() => CheckShutdown(false);
#endif

        // Should be called only by `OvrAvatarManager` during shutdown
        internal protected static void _AvatarManagerCheckShutdown<U>(OvrAvatarManager manager, U instance)
            where U : OvrSingletonBehaviour<U>
        {
            if (instance is null) { return; }

            OvrAvatarLog.Assert(manager != null, logScope, Instance);
            OvrAvatarLog.Assert(manager._willShutdown, logScope, Instance);
            OvrAvatarLog.Assert(manager == OvrAvatarManager.Instance, logScope, Instance);

            if (instance.IsSingletonInstance)
            {
                instance.CheckShutdown(false);
            }
        }

        ///
        /// Shuts down the instance and asserts that it's null.
        /// This should be called by unit tests during teardown to reset this singleton's state.
        ///
        public static void ResetInstance()
        {
            if (!(Instance is null))
            {
                if (Instance != null)
                {
                    Instance.CheckShutdown(false);
                }
                OvrAvatarLog.Assert(Instance == null, logScope, Instance);
                Instance = null;
            }
        }

    }
}
