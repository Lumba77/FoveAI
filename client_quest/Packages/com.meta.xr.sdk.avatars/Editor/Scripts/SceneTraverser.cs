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

#nullable enable
#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
#endif
using UnityEngine;
using UnityEngine.SceneManagement;
using System;
using System.Linq;

namespace Oculus.Avatar2
{
    public static class SceneTraverser
    {
        public delegate void SceneCallback(Scene scene);

        public delegate void GameObjectCallback(Scene scene, GameObject gameObject);

        public delegate void MonoBehaviourCallback(Scene scene, GameObject gameObject, MonoBehaviour monoBehaviour);

        public delegate void BeforeSceneCloseCallback(Scene scene);


        public static void TraverseAllScenesInProject(
            SceneCallback? sceneCallback = null,
            GameObjectCallback? gameObjectCallback = null,
            MonoBehaviourCallback? monoBehaviourCallback = null,
            BeforeSceneCloseCallback? beforeSceneCloseCallback = null,
            bool skipInternalScenes = false)
        {
#if UNITY_EDITOR
            string[] allScenes = AssetDatabase.FindAssets("t:Scene");
            var scenePathsInProject = allScenes
                .Select(scene => AssetDatabase.GUIDToAssetPath(scene))
                .Where(scenePath =>
                    scenePath.StartsWith("Assets/")); // Only consider scenes within the "Assets/" directory
            Scene activeScene = EditorSceneManager.GetActiveScene();
            foreach (string scenePath in scenePathsInProject)
            {
                // Environments are additive to certain scenes. We usually don't care about them when iterating
                // over all scenes to check things.
                if (OvrAvatarUtility.IsScenePathAnEnvironment(scenePath))
                {
                    continue;
                }

                if (skipInternalScenes)
                {
                    if (scenePath.Contains("Assets/Internal")) // skip internal scenes
                    {
                        continue;
                    }
                }

                Scene scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Additive);
                try
                {
                    sceneCallback?.Invoke(scene);

                    foreach (GameObject rootGameObject in scene.GetRootGameObjects())
                    {
                        TraverseGameObject(scene, rootGameObject, gameObjectCallback, monoBehaviourCallback);
                    }
                    beforeSceneCloseCallback?.Invoke(scene);
                }
                // in case the callback function has an error, we still want to be able to continue and close the
                // additively opened scene.
                catch (Exception e)
                {
                    OvrAvatarLog.LogError($"Error Traversing Scene {scene.name}. Exception {e}");
                }

                // Only unload the scene if it's not the currently active scene
                if (scene != activeScene)
                {
                    EditorSceneManager.CloseScene(scene, true);
                }
            }
#endif
        }

        private static void TraverseGameObject(Scene scene, GameObject gameObject,
            GameObjectCallback? gameObjectCallback, MonoBehaviourCallback? monoBehaviourCallback)
        {
            gameObjectCallback?.Invoke(scene, gameObject);

            foreach (MonoBehaviour monoBehaviour in gameObject.GetComponents<MonoBehaviour>())
            {
                monoBehaviourCallback?.Invoke(scene, gameObject, monoBehaviour);
            }

            foreach (Transform child in gameObject.transform)
            {
                TraverseGameObject(scene, child.gameObject, gameObjectCallback, monoBehaviourCallback);
            }
        }
    }
}
