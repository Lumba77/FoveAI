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

// #define AVATARLOD_DEBUG_LIFECYCLE

using System;
using System.Collections.Generic;
using System.Diagnostics;

using UnityEngine;
using UnityEngine.Profiling;

using CultureInfo = System.Globalization.CultureInfo;

namespace Oculus.Avatar2
{
    /**
     * Per-avatar LOD information.
     * This component is added to every avatar managed by the LOD manager.
     * It is informational and not intended to be changed by the application.
     * @see OvrAvatarLODManager
     */
    public sealed class AvatarLOD : MonoBehaviour, IDisposable
    {
        private const string logScope = "AvatarLOD";

        /// Cached transform for this AvatarLOD
        public Transform? CachedTransform { get; private set; } = null;

        /// The entity whose LOD is managed by this instance
        public OvrAvatarEntity? Entity { get; internal set; } = null;

        // Whether the entity associated with this AvatarLOD is non-null and active
        public bool EntityActive => Entity != null && Entity.isActiveAndEnabled;

        /// True if the avatar has been culled by the LOD manager.
        public bool culled { get; private set; }

        /// If enabled, the overrideLevel value will be used instead of the calculated LOD.
        public bool overrideLOD = false;

        // Whether this instance is valid for use with `AvatarLODManager`
        internal bool IsValid => Entity != null;

        private bool _prevOverrideLOD = false;

        /// Desired level of detail for this avatar.
        public int overrideLevel
        {
            get => Mathf.Clamp(_overrideLevel, -1, maxLodLevel);
            set => _overrideLevel = value;
        }

        // TODO: Initialize to `int.MinValue`?
        private int _overrideLevel = default;
        private int _prevOverrideLevel = default;

        /// Transform on the avatar center joint.
        public Transform? centerXform;

        public readonly List<Transform> extraXforms = new List<Transform>();
        private readonly List<AvatarLODGroup> _lodGroups = new List<AvatarLODGroup>();

        /// Vertex counts for each level of detail for this avatar.
        public readonly List<int> vertexCounts = new List<int>();

        /// Triangle counts for each level of detail for this avatar.
        public readonly List<int> triangleCounts = new List<int>();

        ///Skinning cost for each level of detail for this avatar.
        public readonly List<int> skinningCosts = new List<int>();

        private int _minLodLevel = -1;

        /// Minimum LOD level loaded for this avatar.
        public int minLodLevel => _minLodLevel;

        private int _maxLodLevel = -1;

        /// Maximum LOD level loaded for this avatar.
        public int maxLodLevel => _maxLodLevel;

        /// Distance of avatar center joint from the LOD camera.
        public float distance;

        /// Screen percent occupied by the avatar (0 - 1).
        public float screenPercent;

        /// LOD level calculated based on screen percentage (before dynamic processing).
        public int wantedLevel;

        /// LOD level calculated after dynamic processing.
        public int dynamicLevel;

        ///
        /// Importance of avatar for display purposes (geometric LOD).
        /// This is from a logarithmic function by OvrAvatarLODManager.
        /// @see OvrAvatarLODManager.dynamicLodWantedLogScale
        ///
        public float lodImportance;

        ///
        /// Importance of avatar for update (animation) purposes.
        /// This is from a logarithmic function by OvrAvatarLODManager.
        /// @see OvrAvatarLODManager.screenPercentToUpdateImportanceCurvePower
        ///  @see OvrAvatarLODManager.screenPercentToUpdateImportanceCurveMultiplier.
        ///
        public float updateImportance;

        /// Network streaming fidelity for this avatar.
        public OvrAvatarEntity.StreamLOD dynamicStreamLod;

        /// Event invoked when the avatar's cull status has changed.
        /// This event is also available from OvrAvatarLODManager.
        /// @see OvrAvatarLODManager.CullChangedEvent
        [System.Obsolete("Use `OnCulledChangedEvent` instead")]
        public Action<bool>? CulledChangedEvent;

        /// Event invoked when the avatar's cull status has changed.
        /// This event is also available from OvrAvatarLODManager.
        /// @see OvrAvatarLODManager.OnCullChangedEvent
        public event Action<AvatarLOD, bool>? OnCulledChangedEvent;

        #region sticky LOD changes
        public bool stickyLOD = false;
        // This is the level we want to show
        private float interpolatedLodImportance_;
        // This is the level LOD Manager recommends us to show
        private float targetLodImportance_;
        private int targetLevelDelayed_;
        private float lastLODUpdateTime_;
        private float delayedLodUpdateCountdown_ = 0.0f;
        public float stickyLODTimeDelay = 1.6f;
        public float skipDelayedLodSwitchingCountdown = 1.0f;
        public bool isOutOfSight = false;

        public float LodImportance
        {
            get { return interpolatedLodImportance_; }
            set
            {
                if (!stickyLOD)
                {
                    interpolatedLodImportance_ = targetLodImportance_ = value;
                    return;
                }
                targetLodImportance_ = value;
            }
        }

        public void SetLevelWithImprovementDelay(int targetLevel)
        {
            if (Level == -1 || (!stickyLOD && (Entity != null && Entity.EntityActive)))
            {
                Level = targetLevelDelayed_ = targetLevel;
                return;
            }
            targetLevelDelayed_ = targetLevel;
            if (targetLevel >= Level || skipDelayedLodSwitchingCountdown > 0)
            {
                delayedLodUpdateCountdown_ = 0.0f;
            }
            else
            {
                if (delayedLodUpdateCountdown_ <= 0.0f)
                    delayedLodUpdateCountdown_ = stickyLODTimeDelay;
            }
        }

        private void UpdateStickyLOD()
        {
            float deltaTime = Time.time - lastLODUpdateTime_;
            lastLODUpdateTime_ = Time.time;
            interpolatedLodImportance_ = Mathf.Lerp(interpolatedLodImportance_, targetLodImportance_, deltaTime / stickyLODTimeDelay);
            delayedLodUpdateCountdown_ -= deltaTime;
            if (delayedLodUpdateCountdown_ < 0 && Level != targetLevelDelayed_ && (Entity != null && Entity.EntityActive))
            {
                Level = targetLevelDelayed_;
                delayedLodUpdateCountdown_ = 0.0f;
            }
            skipDelayedLodSwitchingCountdown -= deltaTime;
            skipDelayedLodSwitchingCountdown = Mathf.Max(skipDelayedLodSwitchingCountdown, 0.0f);
        }
        #endregion

        private bool forceDisabled_ = false;

        private int _level;
        private int _prevLevel;

        public int Level
        {
            get => _level;
            set
            {
                if (value == _prevLevel) { return; }
                _level = value;

                // force avatar reskinning when LOD changes or we can see old pose
                if (_level != -1 && !culled)
                {
                    ForceReskinningThisFrame();
                }

                if (!overrideLOD)
                {
                    UpdateLOD();
                    UpdateDebugLabel();
                }

                _prevLevel = _level;
            }
        }

        internal CAPI.ovrAvatar2EntityId EntityId { get; private set; } = CAPI.ovrAvatar2EntityId.Invalid;

        // force reskin avatars on LOD switching
        private bool forceReskinning_;
        private float prevImportance_;
        private float FIRST_PERSON_UPDATE_IMPORTANCE = 10000.0f;

        public void OnRenderableDisposed(OvrAvatarRenderable disposedRenderable)
        {
            foreach (var lodGroup in _lodGroups)
            {
                lodGroup.OnRenderableDisposed(disposedRenderable);
            }
        }

        public void ForceReskinningThisFrame()
        {
            if (!forceReskinning_)
            {
                forceReskinning_ = true;
                prevImportance_ = updateImportance;
                updateImportance = FIRST_PERSON_UPDATE_IMPORTANCE;
                AvatarLODManager.Instance.MinNecessaryAmountOfSkinnings++;
            }
        }

        public UInt32 UpdateCost
        {
            get
            {
                // Clear
                // ASSUMPTION: Not more than 31 lods, so using int as bitfields is sufficient
                UInt32 levelsWithCost = 0;

                // Check costs for all lod groups
                foreach (var lodGroup in _lodGroups) { levelsWithCost |= lodGroup.LevelsWithAnimationUpdateCost; }

                UInt32 cost = 0;
                for (int i = minLodLevel; i <= maxLodLevel; i++)
                {
                    cost += ((levelsWithCost & (1 << i)) != 0) ? (UInt32)skinningCosts[i] : 0;
                }
                return cost;
            }
        }

        private void Awake()
        {
#if UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_STANDALONE_WIN
            _avatarId = ++_avatarIdSource;
#endif // UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_STANDALONE_WIN

            CachedTransform = transform;
        }

        private void Start()
        {
            // sticky LOD changes
            var go = gameObject;
            // Depending on `Start` order, `OvrAvatarEntity` may have already assigned itself as the owning `Entity`,
            // if so - no need to `TryGetComponent`
            if (Entity == null || Entity.gameObject != go)
            {
                if (go.TryGetComponent<OvrAvatarEntity>(out var entity))
                {
                    Entity = entity;
                }
                else
                {
                    OvrAvatarLog.LogError("Failed to find OvrAvatarEntity for AvatarLOD instance!", logScope, this);
                    AvatarLOD.Destroy(this);
                    return;
                }
            }

            // Attempt to add this to the LOD manager, but only if the LOD manager
            // is initialized (it really should be by this point, but if not, the LOD manager
            // will add this during its initialization phase)
            var lodManager = AvatarLODManager.Instance;
            if (lodManager != null && !TryAddToLODManager(lodManager))
            {
                OvrAvatarLog.LogError("Failed to add AvatarLOD instance to AvatarLODManager!", logScope, this);
            }

            lastLODUpdateTime_ = Time.time;
            // ~ sticky LOD changes

            if (centerXform == null) { centerXform = CachedTransform; }

#if AVATARLOD_DEBUG_LIFECYCLE
            OvrAvatarLog.LogWarning($"Created AvatarLOD instance {GetHashCode()}, ent{EntityId}", logScope, this);
#endif // AVATARLOD_DEBUG_LIFECYCLE
        }

        private void OnDestroy()
        {
            var entityId = EntityId;

            Dispose();

#if AVATARLOD_DEBUG_LIFECYCLE
            OvrAvatarLog.LogWarning($"Did destroy AvatarLOD instance {GetHashCode()}, ent{entityId}", logScope, this);
#endif // AVATARLOD_DEBUG_LIFECYCLE
        }

        internal bool TryAddToLODManager(AvatarLODManager manager)
        {
            if (Entity == null)
            {
                EntityId = CAPI.ovrAvatar2EntityId.Invalid;
                return false;
            }

            if (!AvatarLODManager.shuttingDown && !manager.AddLOD(this))
            {
                OvrAvatarLog.LogError("Failed to add AvatarLOD instance!", logScope, this);
                EntityId = CAPI.ovrAvatar2EntityId.Invalid;
                return false;
            }

            EntityId = Entity.internalEntityId;
            return true;
        }

        private void TryRemoveFromLODManager()
        {
            if (EntityId != CAPI.ovrAvatar2EntityId.Invalid)
            {
#if AVATARLOD_DEBUG_LIFECYCLE
                var entityId = EntityId;
#endif // AVATARLOD_DEBUG_LIFECYCLE

                EntityId = CAPI.ovrAvatar2EntityId.Invalid;
                AvatarLODManager.RemoveLOD(this);

#if AVATARLOD_DEBUG_LIFECYCLE
                OvrAvatarLog.LogWarning($"Removed AvatarLOD instance {GetHashCode()}, ent{entityId}", logScope, this);
#endif // AVATARLOD_DEBUG_LIFECYCLE
            }
        }

        private bool _isDisposed = false;
        public void Dispose()
        {
            if (!_isDisposed)
            {
                _isDisposed = true;

#if AVATARLOD_DEBUG_LIFECYCLE
                var entityId = EntityId;
#endif // AVATARLOD_DEBUG_LIFECYCLE

                TryRemoveFromLODManager();
                DestroyLODParentIfOnlyChild();

#pragma warning disable CS0618
                CulledChangedEvent = null;
#pragma warning restore CS0618
                OnCulledChangedEvent = null;

                extraXforms.Clear();

                Entity = null;

                _lodGroups.Clear();

#if AVATARLOD_DEBUG_LIFECYCLE
                OvrAvatarLog.LogWarning($"Did dispose AvatarLOD instance {GetHashCode()}, ent{entityId}", logScope, this);
#endif // AVATARLOD_DEBUG_LIFECYCLE
            }
        }

        // Returns true upon a state transition
        public bool SetCulled(bool nextCulled)
        {
            if (nextCulled == culled) { return false; }

            culled = nextCulled;
#pragma warning disable CS0618
            CulledChangedEvent?.Invoke(culled);
#pragma warning restore CS0618
            OnCulledChangedEvent?.Invoke(this, culled);
            return true;
        }

        public bool hasOverride()
        {
            return overrideLOD || _prevOverrideLOD;
        }

        private readonly List<AvatarLODParent> _parentsCache = new();

        private bool HasValidLODParent()
        {
            CachedTransform?.parent.GetComponents(_parentsCache);

            bool found = false;
            foreach (var lodParent in _parentsCache)
            {
                if (!lodParent.beingDestroyed)
                {
                    found = true;
                    break;
                }
            }
            _parentsCache.Clear();
            return found;
        }

        private void DestroyLODParentIfOnlyChild()
        {
            Transform? cachedParent = CachedTransform != null ? CachedTransform.parent : null;
            if (cachedParent != null)
            {
                cachedParent.gameObject.GetComponents(_parentsCache);
                foreach (var lodParent in _parentsCache) { lodParent.DestroyIfOnlyLODChild(this); }
                _parentsCache.Clear();
            }
        }


        private void OnBeforeTransformParentChanged()
        {
            DestroyLODParentIfOnlyChild();
        }

        private void OnTransformParentChanged()
        {
            Transform? parentTx = CachedTransform?.parent;
            if (parentTx != null && !HasValidLODParent()) { parentTx.gameObject.AddComponent<AvatarLODParent>(); }

            AvatarLODManager.ParentStateChanged(this);
        }

        internal void ResetForceReskinning()
        {
            if (forceReskinning_)
            {
                forceReskinning_ = false;
                updateImportance = prevImportance_;
                AvatarLODManager.Instance.MinNecessaryAmountOfSkinnings--;
            }
        }

        // This behaviour is manually updated at a specific time during OvrAvatarManager::Update()
        // to prevent issues with Unity script update ordering
        internal void UpdateOverride()
        {
            ResetForceReskinning();
            if (!isActiveAndEnabled || forceDisabled_) { return; }

            Profiler.BeginSample("AvatarLOD::UpdateOverride");

            //sticky LOD changes
            if (stickyLOD)
            {
                UpdateStickyLOD();
            }
            //~sticky LOD changes

            bool needsUpdateLod = (overrideLOD && overrideLevel != _prevOverrideLevel) ||
                                  (overrideLOD != _prevOverrideLOD);

            _prevOverrideLevel = overrideLevel;
            _prevOverrideLOD = overrideLOD;

            if (needsUpdateLod) { UpdateLOD(); }

#if UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_STANDALONE_WIN
            var needsDebugLabelUpdate = AvatarLODManager.Instance.debug.displayLODLabels ||
                                        AvatarLODManager.Instance.debug.displayAgeLabels ||
                                        AvatarLODManager.Instance.debug.displayUpdateDelayLabels;

            if (needsDebugLabelUpdate || needsUpdateLod) { UpdateDebugLabel(); }
#endif // UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_STANDALONE_WIN

            Profiler.EndSample();
        }

        private void UpdateLOD()
        {
            if (forceDisabled_) { return; }

            if (_lodGroups != null && _lodGroups.Count > 0)
            {
                foreach (var lodGroup in _lodGroups) { lodGroup.Level = overrideLOD ? overrideLevel : Level; }
            }
        }

        private void AddLODGroup(AvatarLODGroup group)
        {
            _lodGroups.Add(group);
            group.parentLOD = this;
            group.Level = overrideLOD ? overrideLevel : Level;
        }

        internal void RemoveLODGroup(AvatarLODGroup group)
        {
            _lodGroups.Remove(group);
        }

        internal void ClearLODGameObjects()
        {
            // Vertex counts will be reset by this function.
            vertexCounts.Clear();
            triangleCounts.Clear();
            skinningCosts.Clear();

            _minLodLevel = -1;
            _maxLodLevel = -1;

#if UNITY_EDITOR || DEVELOPMENT_BUILD
            CAPI.ovrAvatar2LOD_UnregisterAvatar(_avatarId);
#endif // UNITY_EDITOR || DEVELOPMENT_BUILD
        }

        public void AddLODGameObjectGroupByAvatarSkinnedMeshRenderers(GameObject parentGameObject, Dictionary<string, List<GameObject>> suffixToObj)
        {
            foreach (var kvp in suffixToObj)
            {
                AvatarLODSkinnableGroup gameObjectGroup = parentGameObject.GetOrAddComponent<AvatarLODSkinnableGroup>();
                gameObjectGroup.GameObjects = kvp.Value.ToArray();
                AddLODGroup(gameObjectGroup);
            }
        }

        public void AddLODGameObjectGroupBySdkRenderers(Dictionary<int, OvrAvatarEntity.LodData> lodObjects)
        {
            // Vertex counts will be reset by this function.
            vertexCounts.Clear();
            triangleCounts.Clear();
            skinningCosts.Clear();

            vertexCounts.Capacity = (int)CAPI.ovrAvatar2EntityLODFlagsCount;
            triangleCounts.Capacity = (int)CAPI.ovrAvatar2EntityLODFlagsCount;
            skinningCosts.Capacity = (int)CAPI.ovrAvatar2EntityLODFlagsCount;
            for (uint i = 0; i < CAPI.ovrAvatar2EntityLODFlagsCount; ++i)
            {
                vertexCounts.Add(0);
                triangleCounts.Add(0);
                skinningCosts.Add(0);
            }

            if (lodObjects.Count > 0)
            {
                // first see what the limits could be...
                _minLodLevel = int.MaxValue;
                _maxLodLevel = int.MinValue;

                foreach (var entry in lodObjects)
                {
                    int lodIndex = entry.Key;
                    if (_minLodLevel > lodIndex) { _minLodLevel = lodIndex; }
                    if (_maxLodLevel < lodIndex) { _maxLodLevel = lodIndex; }
                }

                OvrAvatarLog.LogVerbose($"Set lod range (min:{_minLodLevel}, max:{_maxLodLevel})", logScope, this);
            }
            else
            {
                OvrAvatarLog.LogError("No LOD data specified", logScope, this);

                _maxLodLevel = _minLodLevel = -1;
            }

            GameObject[] children = new GameObject[maxLodLevel + 1];
            Transform? commonParent = null;
            for (int lodIdx = minLodLevel; lodIdx <= maxLodLevel; ++lodIdx)
            {
                if (lodObjects.TryGetValue(lodIdx, out var lodData))
                {
                    vertexCounts[lodIdx] = lodData.vertexCount;
                    triangleCounts[lodIdx] = lodData.triangleCount;
                    skinningCosts[lodIdx] = lodData.skinningCost;

                    children[lodIdx] = lodData.gameObject;

                    var localParentTx = lodData.transform.parent;

                    OvrAvatarLog.AssertConstMessage(commonParent == null || commonParent == localParentTx
                        , "Expected all lodObjects to have the same parent object.", logScope, this);

                    commonParent = localParentTx;
                }
            }

            if (commonParent != null)
            {
                var gameObjectGroup = commonParent.gameObject.GetOrAddComponent<AvatarLODSkinnableGroup>();
                gameObjectGroup.GameObjects = children;
                AddLODGroup(gameObjectGroup);
            }

#if UNITY_EDITOR || DEVELOPMENT_BUILD
            // Register avatar with native runtime LOD scheme
            // Temporary for LOD editing bring up
            CAPI.ovrAvatar2LODRegistration reg;
            reg.avatarId = _avatarId;
            reg.lodWeights = vertexCounts.ToArray();
            reg.lodThreshold = _maxLodLevel;

            CAPI.ovrAvatar2LOD_RegisterAvatar(reg);
#endif // UNITY_EDITOR || DEVELOPMENT_BUILD
        }

        public void updateLODCost(int lod, OvrAvatarEntity.LodData lodData)
        {
            if (lod < _minLodLevel || _maxLodLevel < lod)
            {
                return;
            }

            vertexCounts[lod] = lodData.vertexCount;
            triangleCounts[lod] = lodData.triangleCount;
            skinningCosts[lod] = lodData.skinningCost;
        }

        public AvatarLODActionGroup AddLODActionGroup(GameObject go, Action[] actions)
        {
            var actionLODGroup = go.GetOrAddComponent<AvatarLODActionGroup>();
            if (actions?.Length > 0)
            {
                actionLODGroup.Actions = new List<Action>(actions);
            }
            AddLODGroup(actionLODGroup);
            return actionLODGroup;
        }

        public AvatarLODActionGroup AddLODActionGroup(GameObject go, Action action, int levels)
        {
            var actions = new Action[levels];
            if (action != null)
            {
                for (int i = 0; i < levels; i++)
                {
                    actions[i] = action;
                }
            }

            return AddLODActionGroup(go, actions);
        }

        // Find a valid LOD near the requested one
        public int CalcAdjustedLod(int lod)
        {
            var adjustedLod = Mathf.Clamp(lod, minLodLevel, maxLodLevel);
            if (adjustedLod != -1 && vertexCounts[adjustedLod] == 0)
            {
                adjustedLod = GetNextLod(lod);
                if (adjustedLod == -1) { adjustedLod = GetPreviousLod(lod); }
            }
            return adjustedLod;
        }

        private int GetNextLod(int lod)
        {
            if (maxLodLevel >= 0)
            {
                for (int nextLod = lod + 1; nextLod <= maxLodLevel; ++nextLod)
                {
                    if (vertexCounts[nextLod] != 0) { return nextLod; }
                }
            }
            return -1;
        }

        internal int GetPreviousLod(int lod)
        {
            if (minLodLevel >= 0)
            {
                for (int prevLod = lod - 1; prevLod >= minLodLevel; --prevLod)
                {
                    if (vertexCounts[prevLod] != 0) { return prevLod; }
                }
            }
            return -1;
        }

        // Returns true when the entity is active and the LODs have been setup.
        public bool AreLodsActive()
        {
            return EntityActive && minLodLevel >= 0 && maxLodLevel >= 0;
        }

        public void Reset()
        {
            ResetXforms();
        }

        private void ResetXforms()
        {
            centerXform = transform;
            extraXforms.Clear();
        }

#if UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_STANDALONE_WIN
        // AvatarLODManager.Initialize doesn't run for all the avatars added
        // in LODScene so assign a unique id internally on construction.
        private static Int32 _avatarIdSource = default;

        // Temporary to bring up runtime LOD system
        // Unique ID for this avatar
        private Int32 _avatarId;
        private GameObject? _debugCanvas;
#endif // UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_STANDALONE_WIN

        /// Clock time since last update (in seconds).
        public float lastUpdateAgeSeconds;

        // the amount of game ticks since last update
        public int lastUpdateAgeTicks = 0;

        /// Total maximum age during previous two updates (in seconds).
        public float previousUpdateAgeWindowSeconds;

        [Conditional("DEVELOPMENT_BUILD")]
        [Conditional("UNITY_EDITOR")]
        internal void TrackUpdateAge(float deltaTime)
        {
#if UNITY_EDITOR || DEVELOPMENT_BUILD
            // Track of the last update time for debug tools
            if (EntityActive)
            {
                previousUpdateAgeWindowSeconds = lastUpdateAgeSeconds + deltaTime;
                lastUpdateAgeSeconds = 0;
            }
            else { lastUpdateAgeSeconds += Time.deltaTime; }
#endif // UNITY_EDITOR || DEVELOPMENT_BUILD
        }

        [Conditional("DEVELOPMENT_BUILD")]
        [Conditional("UNITY_EDITOR")]
        [Conditional("UNITY_STANDALONE_WIN")]
        public void UpdateDebugLabel()
        {
#if UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_STANDALONE_WIN
            if (AvatarLODManager.Instance.debug.displayLODLabels || AvatarLODManager.Instance.debug.displayAgeLabels || AvatarLODManager.Instance.debug.displayUpdateDelayLabels)
            {
                if (_debugCanvas == null && AvatarLODManager.Instance.avatarLodDebugCanvas != null)
                {
                    GameObject
                        canvasPrefab
                            = AvatarLODManager.Instance
                                .avatarLodDebugCanvas; //LoadAssetWithFullPath<GameObject>($"{AvatarPaths.ASSET_SOURCE_PATH}/LOD/Prefabs/AVATAR_LOD_DEBUG_CANVAS.prefab");
                    if (canvasPrefab != null)
                    {
                        _debugCanvas = Instantiate(canvasPrefab, centerXform);

                        // Set position instead of localPosition to keep the label in a steady readable location.
                        _debugCanvas.transform.position = _debugCanvas.transform.parent.position +
                                                          AvatarLODManager.Instance.debug.displayLODLabelOffset;

                        _debugCanvas.SetActive(true);
                    }
                    else
                    {
                        OvrAvatarLog.LogWarning(
                            "DebugLOD will require the avatarLodDebugCanvas prefab to be specified. This has a simple UI card that allows for world space display of LOD.");
                    }
                }

                if (_debugCanvas != null)
                {
                    var text = _debugCanvas.GetComponentInChildren<UnityEngine.UI.Text>();

                    // Set position instead of localPosition to keep the label in a steady readable location.
                    _debugCanvas.transform.position = _debugCanvas.transform.parent.position +
                                                      AvatarLODManager.Instance.debug.displayLODLabelOffset;

                    if (AvatarLODManager.Instance.debug.displayLODLabels)
                    {
                        int actualLevel = overrideLOD ? overrideLevel : Level;
                        text.color = actualLevel == -1 ? Color.gray : AvatarLODManager.LOD_COLORS[actualLevel];
                        text.text = actualLevel.ToString();
                        text.fontSize = 40;
                    }

                    if (AvatarLODManager.Instance.debug.displayAgeLabels)
                    {
                        text.text = previousUpdateAgeWindowSeconds.ToString(CultureInfo.InvariantCulture);
                        text.color = new Color(
                            Math.Max(Math.Min(-1.0f + 2.0f * previousUpdateAgeWindowSeconds, 1.0f), 0.0f)
                            , Math.Max(
                                Math.Min(
                                    previousUpdateAgeWindowSeconds * 2.0f, 2.0f - 2.0f * previousUpdateAgeWindowSeconds)
                                , 0f), Math.Max(Math.Min(1.0f - 2.0f * previousUpdateAgeWindowSeconds, 1.0f), 0.0f));
                        text.fontSize = 10;
                    }

                    if (AvatarLODManager.Instance.debug.displayUpdateDelayLabels) {
                      string debugStr = $"{lastUpdateAgeTicks}\nticks";
                      if (lastUpdateAgeTicks > 20) {
                        text.color = Color.red;
                        debugStr += "!!!!!!";
                      } else if (lastUpdateAgeTicks > 10) {
                        text.color = Color.yellow;
                        debugStr += "!!!";
                      } else {
                        text.color = Color.green;
                      }

                      text.text = debugStr;
                      text.fontSize = 20;
                    }
                }
            }
            else
            {
                if (_debugCanvas != null)
                {
                    _debugCanvas.SetActive(false);
                    Destroy(_debugCanvas);
                    _debugCanvas = null;
                }
            }
#endif // UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_STANDALONE_WIN
        }

        [Conditional("DEVELOPMENT_BUILD")]
        [Conditional("UNITY_EDITOR")]
        [Conditional("UNITY_STANDALONE_WIN")]
        internal void ForceUpdateLOD<T>()
        {
            foreach (var lodGroup in _lodGroups)
            {
                if (lodGroup is T) { lodGroup.UpdateLODGroup(); }
            }
        }
    }
}
