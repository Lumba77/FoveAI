using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using FoveAI.Creative;

namespace FoveAI.Games
{
    /// <summary>
    /// VR Game Engine — spawn characters, enemies, and play games with Alice.
    ///
    /// Games:
    ///   1. Monster Hunt — monsters emerge from walls, shoot them with trigger
    ///   2. Target Practice — floating targets, score points
    ///   3. Character Companion — spawn friendly NPCs that interact with Alice
    ///   4. Tower Defense — place towers, defend against waves
    ///
    /// Characters have:
    ///   • Health, AI behavior, animations (procedural)
    ///   • Can be friendly (follow Alice) or hostile (attack player)
    ///   • Spawn from walls/floor/ceiling
    ///   • Ragdoll on death
    /// </summary>
    public class VRGameEngine : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAI.IPC.FoveAIWebSocketClient wsClient;
        [SerializeField] private AmbientMusicPlayer musicPlayer;

        [Header("Prefabs")]
        [Tooltip("If set, use this as monster prefab. Otherwise generated procedurally.")]
        [SerializeField] private GameObject monsterPrefab;
        [SerializeField] private GameObject targetPrefab;
        [SerializeField] private GameObject characterPrefab;

        [Header("Game Settings")]
        public float spawnRadius = 3f;
        public float spawnHeight = 1.5f;
        public int maxMonsters = 8;
        public float monsterSpeed = 1.2f;
        public float monsterDamage = 10f;
        public float playerHealth = 100f;
        public float shootRange = 20f;
        public float shootDamage = 25f;

        [Header("Visual")]
        public Material monsterMaterial;
        public Material friendlyMaterial;
        public Material targetMaterial;
        public Color hitFlashColor = Color.red;
        public float hitFlashDuration = 0.15f;

        // ── State ──
        public enum GameMode { None, MonsterHunt, TargetPractice, CharacterCompanion, TowerDefense }
        public GameMode CurrentMode { get; private set; } = GameMode.None;

        private readonly List<GameEntity> _entities = new List<GameEntity>();
        private int _score;
        private float _health;
        private int _wave;
        private float _spawnTimer;
        private float _spawnInterval = 3f;
        private bool _gameActive;
        private float _gameStartTime;

        // HUD
        private Canvas _gameHud;
        private TMP_Text _scoreText;
        private TMP_Text _healthText;
        private TMP_Text _waveText;
        private TMP_Text _modeText;

        // ── Entity class ──
        private class GameEntity
        {
            public GameObject obj;
            public float health;
            public float maxHealth;
            public bool isHostile;
            public bool isAlive = true;
            public Renderer renderer;
            public Material originalMaterial;
            public float hitFlashTimer;
            public Vector3 velocity;
            public float attackTimer;
            public enum AIState { Spawning, Idle, Chasing, Attacking, Fleeing, Following, Dead }
            public AIState state = AIState.Spawning;
            public float spawnAnimTime;
        }

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            if (musicPlayer == null) musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();
            _health = playerHealth;
            BuildGameHud();
        }

        private void Update()
        {
            if (!_gameActive) return;

            // Spawn logic
            _spawnTimer += Time.deltaTime;
            if (_spawnTimer >= _spawnInterval && _entities.Count < maxMonsters)
            {
                _spawnTimer = 0f;
                SpawnEntity();
            }

            // Update entities
            UpdateEntities();

            // Shooting
            if (OVRInput.GetDown(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.RTouch) ||
                OVRInput.GetDown(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.LTouch))
            {
                TryShoot();
            }

            // Update HUD
            UpdateHud();

            // Check game over
            if (_health <= 0)
            {
                GameOver();
            }
        }

        // ── Game Mode Management ──

        public void StartGame(GameMode mode)
        {
            StopGame();
            CurrentMode = mode;
            _gameActive = true;
            _score = 0;
            _health = playerHealth;
            _wave = 1;
            _spawnTimer = 0f;
            _gameStartTime = Time.time;

            switch (mode)
            {
                case GameMode.MonsterHunt:
                    _spawnInterval = 3f;
                    maxMonsters = 8;
                    if (musicPlayer != null) musicPlayer.SetMood("energetic");
                    ShowHud(true);
                    _modeText.text = "MONSTER HUNT";
                    break;

                case GameMode.TargetPractice:
                    _spawnInterval = 2f;
                    maxMonsters = 5;
                    if (musicPlayer != null) musicPlayer.SetMood("focused");
                    ShowHud(true);
                    _modeText.text = "TARGET PRACTICE";
                    // Spawn initial targets
                    for (int i = 0; i < 5; i++) SpawnEntity();
                    break;

                case GameMode.CharacterCompanion:
                    _spawnInterval = 999f; // Don't auto-spawn
                    maxMonsters = 3;
                    if (musicPlayer != null) musicPlayer.SetMood("happy");
                    ShowHud(true);
                    _modeText.text = "COMPANION MODE";
                    // Spawn friendly characters
                    for (int i = 0; i < 2; i++) SpawnEntity(friendly: true);
                    break;

                case GameMode.TowerDefense:
                    _spawnInterval = 4f;
                    maxMonsters = 10;
                    if (musicPlayer != null) musicPlayer.SetMood("energetic");
                    ShowHud(true);
                    _modeText.text = "TOWER DEFENSE";
                    break;
            }

            Debug.Log($"[VRGameEngine] Started {mode}");
        }

        public void StopGame()
        {
            _gameActive = false;
            foreach (var ent in _entities)
            {
                if (ent.obj != null) Destroy(ent.obj);
            }
            _entities.Clear();
            ShowHud(false);
            CurrentMode = GameMode.None;
        }

        private void GameOver()
        {
            Debug.Log($"[VRGameEngine] Game Over! Score: {_score}, Wave: {_wave}");
            if (_modeText != null) _modeText.text = $"GAME OVER — Score: {_score}";
            StartCoroutine(GameOverCoroutine());
        }

        private IEnumerator GameOverCoroutine()
        {
            yield return new WaitForSeconds(3f);
            StopGame();
        }

        // ── Spawning ──

        private void SpawnEntity(bool friendly = false)
        {
            // Determine spawn position — from a wall-like edge
            Vector3 spawnPos = GetSpawnPosition();
            Quaternion spawnRot = Quaternion.LookRotation((Camera.main.transform.position - spawnPos).normalized);

            GameObject obj;
            GameEntity entity = new GameEntity();

            if (CurrentMode == GameMode.TargetPractice && targetPrefab != null)
            {
                obj = Instantiate(targetPrefab, spawnPos, spawnRot);
                entity.isHostile = false;
                entity.maxHealth = 1;
            }
            else if (CurrentMode == GameMode.CharacterCompanion || friendly)
            {
                obj = CreateCharacter(spawnPos, spawnRot, friendly: true);
                entity.isHostile = false;
                entity.maxHealth = 50;
            }
            else
            {
                obj = CreateMonster(spawnPos, spawnRot);
                entity.isHostile = true;
                entity.maxHealth = 50;
            }

            entity.obj = obj;
            entity.health = entity.maxHealth;
            entity.renderer = obj.GetComponentInChildren<Renderer>();
            if (entity.renderer != null) entity.originalMaterial = entity.renderer.material;
            entity.state = GameEntity.AIState.Spawning;
            entity.spawnAnimTime = 0f;

            _entities.Add(entity);
        }

        private Vector3 GetSpawnPosition()
        {
            // Spawn from room edges (simulating walls)
            float angle = Random.Range(0f, 360f);
            Vector3 playerPos = Camera.main != null ? Camera.main.transform.position : Vector3.zero;
            Vector3 dir = new Vector3(Mathf.Cos(angle), 0, Mathf.Sin(angle));
            Vector3 pos = playerPos + dir * spawnRadius;
            pos.y = spawnHeight + Random.Range(-0.3f, 0.5f);
            return pos;
        }

        private GameObject CreateMonster(Vector3 pos, Quaternion rot)
        {
            if (monsterPrefab != null)
                return Instantiate(monsterPrefab, pos, rot);

            // Procedural monster — a menacing floating entity
            var go = new GameObject($"Monster_{_entities.Count}");
            go.transform.position = pos;
            go.transform.rotation = rot;

            // Body — elongated sphere
            var body = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.4f, 0.6f, 0.4f);
            body.transform.localPosition = Vector3.zero;
            var bodyRend = body.GetComponent<Renderer>();
            if (monsterMaterial != null) bodyRend.material = monsterMaterial;
            else
            {
                var mat = new Material(Shader.Find("Standard"));
                mat.color = new Color(0.8f, 0.1f, 0.1f, 1f);
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", new Color(0.5f, 0.05f, 0.05f));
                bodyRend.material = mat;
            }

            // Eyes — glowing red
            for (int i = 0; i < 2; i++)
            {
                var eye = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                eye.transform.SetParent(go.transform, false);
                eye.transform.localScale = Vector3.one * 0.08f;
                eye.transform.localPosition = new Vector3(i == 0 ? -0.12f : 0.12f, 0.15f, 0.3f);
                var eyeRend = eye.GetComponent<Renderer>();
                var eyeMat = new Material(Shader.Find("Standard"));
                eyeMat.color = Color.yellow;
                eyeMat.EnableKeyword("_EMISSION");
                eyeMat.SetColor("_EmissionColor", Color.red * 3f);
                eyeRend.material = eyeMat;
            }

            // Add collider for hit detection
            var col = go.AddComponent<SphereCollider>();
            col.radius = 0.5f;

            return go;
        }

        private GameObject CreateCharacter(Vector3 pos, Quaternion rot, bool friendly)
        {
            if (characterPrefab != null)
                return Instantiate(characterPrefab, pos, rot);

            // Procedural friendly character — a glowing orb companion
            var go = new GameObject($"Companion_{_entities.Count}");
            go.transform.position = pos;
            go.transform.rotation = rot;

            var body = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = Vector3.one * 0.3f;
            var rend = body.GetComponent<Renderer>();
            if (friendlyMaterial != null) rend.material = friendlyMaterial;
            else
            {
                var mat = new Material(Shader.Find("Standard"));
                mat.color = new Color(0.3f, 0.8f, 1f, 1f);
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", new Color(0.1f, 0.3f, 0.5f) * 2f);
                rend.material = mat;
            }

            var col = go.AddComponent<SphereCollider>();
            col.radius = 0.35f;

            return go;
        }

        // ── Entity AI ──

        private void UpdateEntities()
        {
            Vector3 playerPos = Camera.main != null ? Camera.main.transform.position : Vector3.zero;

            for (int i = _entities.Count - 1; i >= 0; i--)
            {
                var ent = _entities[i];
                if (ent.obj == null || !ent.isAlive) continue;

                // Hit flash
                if (ent.hitFlashTimer > 0)
                {
                    ent.hitFlashTimer -= Time.deltaTime;
                    if (ent.renderer != null && ent.originalMaterial != null)
                    {
                        if (ent.hitFlashTimer <= 0)
                            ent.renderer.material = ent.originalMaterial;
                    }
                }

                // Spawn animation
                if (ent.state == GameEntity.AIState.Spawning)
                {
                    ent.spawnAnimTime += Time.deltaTime;
                    ent.obj.transform.localScale = Vector3.Lerp(Vector3.zero, Vector3.one, ent.spawnAnimTime * 3f);
                    if (ent.spawnAnimTime >= 0.5f)
                    {
                        ent.state = ent.isHostile ? GameEntity.AIState.Chasing : GameEntity.AIState.Following;
                    }
                    continue;
                }

                // AI behavior
                float distToPlayer = Vector3.Distance(ent.obj.transform.position, playerPos);

                if (ent.isHostile)
                {
                    switch (ent.state)
                    {
                        case GameEntity.AIState.Chasing:
                            // Move toward player
                            Vector3 dir = (playerPos - ent.obj.transform.position).normalized;
                            ent.obj.transform.position += dir * monsterSpeed * Time.deltaTime;
                            ent.obj.transform.rotation = Quaternion.LookRotation(dir);

                            // Bob up and down
                            ent.obj.transform.position += Vector3.up * Mathf.Sin(Time.time * 3f + i) * 0.005f;

                            if (distToPlayer < 1.5f)
                                ent.state = GameEntity.AIState.Attacking;
                            break;

                        case GameEntity.AIState.Attacking:
                            // Attack player
                            ent.attackTimer += Time.deltaTime;
                            if (ent.attackTimer >= 1f)
                            {
                                ent.attackTimer = 0f;
                                _health -= monsterDamage;
                                // Knockback
                                ent.obj.transform.position -= ent.obj.transform.forward * 0.5f;
                                ent.state = GameEntity.AIState.Chasing;
                            }
                            break;
                    }
                }
                else
                {
                    // Friendly — follow player at distance
                    if (ent.state == GameEntity.AIState.Following)
                    {
                        if (distToPlayer > 2.5f)
                        {
                            Vector3 dir = (playerPos - ent.obj.transform.position).normalized;
                            ent.obj.transform.position += dir * 0.8f * Time.deltaTime;
                        }
                        // Orbit gently
                        ent.obj.transform.RotateAround(playerPos, Vector3.up, 15f * Time.deltaTime);
                    }
                }
            }
        }

        // ── Shooting ──

        private void TryShoot()
        {
            // Try right hand first, then left
            Transform hand = GetHandTransform(OVRInput.Controller.RTouch);
            if (hand == null) hand = GetHandTransform(OVRInput.Controller.LTouch);
            if (hand == null) return;

            Ray ray = new Ray(hand.position, hand.forward);
            Debug.DrawRay(ray.origin, ray.direction * shootRange, Color.cyan, 0.5f);

            // Check entity hits
            GameEntity closestHit = null;
            float closestDist = shootRange;

            foreach (var ent in _entities)
            {
                if (ent.obj == null || !ent.isAlive) continue;
                var col = ent.obj.GetComponent<Collider>();
                if (col == null) col = ent.obj.GetComponentInChildren<Collider>();
                if (col == null) continue;

                if (col.Raycast(ray, out RaycastHit hit, shootRange))
                {
                    float dist = Vector3.Distance(ray.origin, hit.point);
                    if (dist < closestDist)
                    {
                        closestDist = dist;
                        closestHit = ent;
                    }
                }
            }

            if (closestHit != null)
            {
                HitEntity(closestHit, shootDamage);
            }

            // Haptic feedback
            OVRInput.SetControllerVibration(0.1f, 0.3f, OVRInput.Controller.RTouch);
        }

        private void HitEntity(GameEntity ent, float damage)
        {
            ent.health -= damage;

            // Flash hit
            if (ent.renderer != null)
            {
                var flashMat = new Material(Shader.Find("Standard"));
                flashMat.color = hitFlashColor;
                flashMat.EnableKeyword("_EMISSION");
                flashMat.SetColor("_EmissionColor", hitFlashColor * 2f);
                ent.renderer.material = flashMat;
                ent.hitFlashTimer = hitFlashDuration;
            }

            if (ent.health <= 0)
            {
                KillEntity(ent);
            }
        }

        private void KillEntity(GameEntity ent)
        {
            ent.isAlive = false;
            ent.state = GameEntity.AIState.Dead;

            // Death animation — shrink and fade
            StartCoroutine(DeathAnimation(ent));

            // Score
            if (ent.isHostile) _score += 10;
            else _score += 5;

            // Spawn replacement for target practice
            if (CurrentMode == GameMode.TargetPractice)
            {
                StartCoroutine(SpawnAfterDelay(1f));
            }
        }

        private IEnumerator DeathAnimation(GameEntity ent)
        {
            if (ent.obj == null) yield break;
            Vector3 startScale = ent.obj.transform.localScale;
            float t = 0f;
            while (t < 0.5f && ent.obj != null)
            {
                t += Time.deltaTime;
                ent.obj.transform.localScale = Vector3.Lerp(startScale, Vector3.zero, t * 2f);
                ent.obj.transform.Rotate(Vector3.up, 720f * Time.deltaTime);
                yield return null;
            }
            if (ent.obj != null) Destroy(ent.obj);
            _entities.Remove(ent);
        }

        private IEnumerator SpawnAfterDelay(float delay)
        {
            yield return new WaitForSeconds(delay);
            if (_gameActive) SpawnEntity();
        }

        // ── Wave System ──

        private void NextWave()
        {
            _wave++;
            _spawnInterval = Mathf.Max(0.5f, _spawnInterval * 0.85f);
            monsterSpeed *= 1.1f;
            monsterDamage *= 1.05f;
            Debug.Log($"[VRGameEngine] Wave {_wave} — faster spawns, stronger monsters");
        }

        // ── HUD ──

        private void BuildGameHud()
        {
            var hudGo = new GameObject("GameHUD");
            hudGo.transform.SetParent(transform);
            _gameHud = hudGo.AddComponent<Canvas>();
            _gameHud.renderMode = RenderMode.WorldSpace;
            _gameHud.enabled = false;

            var rt = hudGo.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(400, 120);
            rt.localScale = Vector3.one * 0.002f;
            rt.position = new Vector3(0, 2.5f, 2f);

            var bg = hudGo.AddComponent<Image>();
            bg.color = new Color(0.02f, 0.03f, 0.06f, 0.85f);

            var font = TMP_Settings.defaultFontAsset;

            // Mode text (top center)
            _modeText = CreateText("ModeText", hudGo.transform, new Vector2(0, 30), new Vector2(380, 30), font, 20, new Color(0.3f, 0.7f, 1f, 1f));
            _modeText.alignment = TextAlignmentOptions.Center;

            // Score (left)
            _scoreText = CreateText("ScoreText", hudGo.transform, new Vector2(-130, -10), new Vector2(180, 30), font, 18, Color.white);
            _scoreText.text = "Score: 0";

            // Health (center)
            _healthText = CreateText("HealthText", hudGo.transform, new Vector2(0, -10), new Vector2(180, 30), font, 18, Color.white);
            _healthText.text = "HP: 100";

            // Wave (right)
            _waveText = CreateText("WaveText", hudGo.transform, new Vector2(130, -10), new Vector2(180, 30), font, 18, Color.white);
            _waveText.text = "Wave: 1";
        }

        private TMP_Text CreateText(string name, Transform parent, Vector2 pos, Vector2 size, TMP_FontAsset font, float fontSize, Color color)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var txt = go.AddComponent<TextMeshProUGUI>();
            txt.font = font;
            txt.fontSize = fontSize;
            txt.color = color;
            txt.alignment = TextAlignmentOptions.Center;
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.5f, 0.5f);
            rt.anchorMax = new Vector2(0.5f, 0.5f);
            rt.sizeDelta = size;
            rt.anchoredPosition = pos;
            return txt;
        }

        private void ShowHud(bool show)
        {
            if (_gameHud != null) _gameHud.enabled = show;
        }

        private void UpdateHud()
        {
            if (_scoreText != null) _scoreText.text = $"Score: {_score}";
            if (_healthText != null)
            {
                _healthText.text = $"HP: {Mathf.Max(0, (int)_health)}";
                _healthText.color = _health > 50 ? Color.white : _health > 25 ? Color.yellow : Color.red;
            }
            if (_waveText != null) _waveText.text = $"Wave: {_wave}";

            // Position HUD in front of player
            if (_gameHud != null && Camera.main != null)
            {
                var cam = Camera.main.transform;
                _gameHud.transform.position = cam.position + cam.forward * 2f + Vector3.up * 0.5f;
                _gameHud.transform.rotation = Quaternion.LookRotation(cam.forward);
            }

            // Wave progression
            if (Time.time - _gameStartTime > 30f * _wave && CurrentMode == GameMode.MonsterHunt)
            {
                NextWave();
                _gameStartTime = Time.time;
            }
        }

        // ── Helpers ──

        private Transform GetHandTransform(OVRInput.Controller controller)
        {
            if (_tempTransform == null) _tempTransform = new GameObject("TempHand").transform;
            _tempTransform.position = OVRInput.GetLocalControllerPosition(controller);
            _tempTransform.rotation = OVRInput.GetLocalControllerRotation(controller);
            return _tempTransform;
        }

        private Transform _tempTransform;

        // ── Alice Integration ──

        /// <summary>
        /// Alice can spawn a monster at a specific position via WebSocket.
        /// </summary>
        public void AliceSpawnMonster(Vector3 position)
        {
            if (!_gameActive) return;
            var go = CreateMonster(position, Quaternion.identity);
            var ent = new GameEntity
            {
                obj = go, health = 50, maxHealth = 50, isHostile = true, isAlive = true,
                renderer = go.GetComponentInChildren<Renderer>(),
                state = GameEntity.AIState.Spawning, spawnAnimTime = 0f,
            };
            _entities.Add(ent);
        }

        public int Score => _score;
        public int Wave => _wave;
        public float Health => _health;
        public bool IsActive => _gameActive;
    }
}
