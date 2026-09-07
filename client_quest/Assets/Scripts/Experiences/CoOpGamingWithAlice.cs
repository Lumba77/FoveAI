using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;

namespace FoveAI.Experiences
{
    /// <summary>
    /// Co-Op Gaming with Alice — Alice plays alongside you, not just as a companion.
    ///
    /// Alice has her own avatar, her own controller, and her own strategy.
    /// She communicates, coordinates, celebrates, and teases.
    ///
    /// Game Modes:
    ///   • CoopShooter — fight waves of enemies together
    ///   • PuzzleDuo — solve puzzles that need two players
    ///   • RacingDuo — race against each other or together on a track
    ///   • DefenseDuo — protect a core from both sides
    ///   • TreasureHunt — find hidden treasures, Alice gives hints
    ///   • BuildingChallenge — build structures together
    ///
    /// Alice's play style:
    ///   • Adaptive difficulty — she matches your skill
    ///   • Communicates intent ("I'll take left", "cover me")
    ///   • Celebrates wins ("nice shot!", "we did it!")
    ///   • Teases losses ("you missed!", "my turn to carry")
    ///   • Learns from your style over time
    /// </summary>
    public class CoOpGamingWithAlice : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private Transform aliceTransform;
        [SerializeField] private Transform aliceHead;
        [SerializeField] private Transform aliceRightHand;
        [SerializeField] private Transform aliceLeftHand;

        [Header("Alice Play Settings")]
        public float aliceMoveSpeed = 1.2f;
        public float aliceReactionTime = 0.3f;
        public float aliceAccuracy = 0.75f;  // 0-1, how well she aims
        public float aliceAggression = 0.6f;  // 0-1, how aggressively she plays
        public float aliceSupportiveness = 0.8f;  // 0-1, how much she helps you
        public float communicationInterval = 5f;

        // ── Game Modes ──
        public enum CoopGameMode
        {
            CoopShooter,
            PuzzleDuo,
            RacingDuo,
            DefenseDuo,
            TreasureHunt,
            BuildingChallenge,
        }

        public CoopGameMode CurrentMode { get; private set; }
        public bool IsPlaying { get; private set; }
        public int PlayerScore { get; private set; }
        public int AliceScore { get; private set; }
        public int TeamScore => PlayerScore + AliceScore;

        // ── State ──
        private readonly List<GameObject> _enemies = new();
        private readonly List<GameObject> _treasures = new();
        private readonly List<GameObject> _projectiles = new();
        private GameObject _aliceWeapon;
        private GameObject _playerCore;
        private GameObject _aliceTarget;
        private float _commTimer;
        private float _gameTimer;
        private int _waveNumber;
        private bool _aliceReloading;
        private float _aliceReloadTimer;
        private Vector3 _aliceHomePos;

        // ── Communication Lines ──
        private static readonly string[] CoopComms =
        {
            "i've got your back",
            "taking the left side",
            "cover me, reloading",
            "nice shot!",
            "on your right!",
            "let's push forward",
            "fall back, regroup",
            "i see one more",
            "watch out behind you",
            "we make a good team",
            "my turn to carry",
            "you missed that one",
            "focus fire",
            "i'll distract, you flank",
            "clear on my side",
        };

        private static readonly string[] VictoryLines =
        {
            "we did it!",
            "perfect teamwork",
            "i couldn't have done it without you",
            "that was intense",
            "we're unstoppable",
        };

        private static readonly string[] DefeatLines =
        {
            "so close...",
            "we'll get them next time",
            "my fault, i should've covered",
            "they got us",
            "rematch?",
        };

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (aliceTransform == null)
            {
                var avatar = GameObject.Find("Alice") ?? GameObject.Find("Avatar");
                if (avatar != null)
                {
                    aliceTransform = avatar.transform;
                    aliceHead = avatar.transform.Find("Head");
                    aliceRightHand = avatar.transform.Find("RightHand");
                    aliceLeftHand = avatar.transform.Find("LeftHand");
                }
            }
        }

        private void Update()
        {
            if (!IsPlaying) return;

            _gameTimer += Time.deltaTime;
            _commTimer += Time.deltaTime;

            switch (CurrentMode)
            {
                case CoopGameMode.CoopShooter:
                    UpdateCoopShooter();
                    break;
                case CoopGameMode.PuzzleDuo:
                    UpdatePuzzleDuo();
                    break;
                case CoopGameMode.RacingDuo:
                    UpdateRacingDuo();
                    break;
                case CoopGameMode.DefenseDuo:
                    UpdateDefenseDuo();
                    break;
                case CoopGameMode.TreasureHunt:
                    UpdateTreasureHunt();
                    break;
                case CoopGameMode.BuildingChallenge:
                    UpdateBuildingChallenge();
                    break;
            }

            // Periodic communication
            if (_commTimer >= communicationInterval)
            {
                _commTimer = 0f + Random.Range(-2f, 3f);
                if (Random.value < 0.6f)
                    AliceSay(CoopComms[Random.Range(0, CoopComms.Length)]);
            }
        }

        // ── Start / Stop ──

        public void StartGame(CoopGameMode mode)
        {
            StopGame();
            CurrentMode = mode;
            IsPlaying = true;
            PlayerScore = 0;
            AliceScore = 0;
            _gameTimer = 0f;
            _commTimer = 0f;
            _waveNumber = 1;
            _aliceHomePos = aliceTransform != null ? aliceTransform.position : Vector3.zero;

            switch (mode)
            {
                case CoopGameMode.CoopShooter:
                    StartCoroutine(InitCoopShooter());
                    break;
                case CoopGameMode.PuzzleDuo:
                    StartCoroutine(InitPuzzleDuo());
                    break;
                case CoopGameMode.RacingDuo:
                    InitRacingDuo();
                    break;
                case CoopGameMode.DefenseDuo:
                    StartCoroutine(InitDefenseDuo());
                    break;
                case CoopGameMode.TreasureHunt:
                    StartCoroutine(InitTreasureHunt());
                    break;
                case CoopGameMode.BuildingChallenge:
                    InitBuildingChallenge();
                    break;
            }

            AliceSay($"let's do this. {mode}.");
            Debug.Log($"[CoOp] Started {mode}");
        }

        public void StopGame()
        {
            IsPlaying = false;

            // Clean up
            foreach (var e in _enemies) if (e != null) Destroy(e);
            _enemies.Clear();
            foreach (var t in _treasures) if (t != null) Destroy(t);
            _treasures.Clear();
            foreach (var p in _projectiles) if (p != null) Destroy(p);
            _projectiles.Clear();
            if (_aliceWeapon != null) Destroy(_aliceWeapon);
            if (_playerCore != null) Destroy(_playerCore);
            if (_aliceTarget != null) Destroy(_aliceTarget);
        }

        // ── Coop Shooter ──

        private IEnumerator InitCoopShooter()
        {
            // Give Alice a weapon
            _aliceWeapon = CreateWeapon(aliceRightHand ?? aliceTransform, new Color(0.3f, 0.8f, 1f));
            yield return new WaitForSeconds(0.5f);
            SpawnWave();
        }

        private void SpawnWave()
        {
            int count = 3 + _waveNumber * 2;
            for (int i = 0; i < count; i++)
            {
                Vector3 pos = GetSpawnPositionAroundPlayer(4f + Random.Range(0f, 3f));
                var enemy = CreateEnemy(pos);
                _enemies.Add(enemy);
            }
            AliceSay($"wave {_waveNumber}. {count} of them.");
        }

        private void UpdateCoopShooter()
        {
            // Alice AI behavior
            if (_aliceReloading)
            {
                _aliceReloadTimer += Time.deltaTime;
                if (_aliceReloadTimer > 1.5f)
                {
                    _aliceReloading = false;
                    _aliceReloadTimer = 0f;
                }
                return;
            }

            // Find nearest enemy
            GameObject nearest = null;
            float nearestDist = float.MaxValue;
            foreach (var e in _enemies)
            {
                if (e == null) continue;
                float d = Vector3.Distance(e.transform.position, aliceTransform.position);
                if (d < nearestDist) { nearestDist = d; nearest = e; }
            }

            if (nearest != null && aliceTransform != null)
            {
                _aliceTarget = nearest;

                // Move to tactical position
                Vector3 tactical = GetTacticalPosition(nearest.transform.position);
                aliceTransform.position = Vector3.MoveTowards(
                    aliceTransform.position, tactical, aliceMoveSpeed * Time.deltaTime);

                // Aim at enemy
                if (aliceHead != null)
                {
                    Vector3 dir = (nearest.transform.position - aliceHead.position).normalized;
                    aliceHead.rotation = Quaternion.Slerp(aliceHead.rotation,
                        Quaternion.LookRotation(dir), Time.deltaTime * 5f);
                }

                // Shoot
                if (Random.value < aliceAccuracy * Time.deltaTime * 3f)
                {
                    ShootAt(nearest, aliceAccuracy);
                    if (Random.value < 0.1f) _aliceReloading = true;
                }
            }

            // Check wave clear
            _enemies.RemoveAll(e => e == null);
            if (_enemies.Count == 0 && _gameTimer > 3f)
            {
                _waveNumber++;
                if (_waveNumber > 10)
                {
                    Victory();
                    return;
                }
                SpawnWave();
            }
        }

        // ── Puzzle Duo ──

        private IEnumerator InitPuzzleDuo()
        {
            // Create puzzle elements — switches that need simultaneous activation
            for (int i = 0; i < 4; i++)
            {
                float angle = (i / 4f) * Mathf.PI * 2f;
                Vector3 pos = GetRoomCenter() + new Vector3(Mathf.Cos(angle) * 2f, 1f, Mathf.Sin(angle) * 2f);
                var puzzle = CreatePuzzleSwitch(pos, i);
                _treasures.Add(puzzle);
            }
            yield return new WaitForSeconds(1f);
            AliceSay("two of us, four switches. ready?");
        }

        private void UpdatePuzzleDuo()
        {
            // Alice moves to switches that need activation
            // Simple AI: find unactivated switch, go to it
            foreach (var sw in _treasures)
            {
                if (sw == null) continue;
                var pc = sw.GetComponent<PuzzleSwitch>();
                if (pc != null && !pc.activated && !pc.aliceActivating)
                {
                    pc.aliceActivating = true;
                    StartCoroutine(AliceActivateSwitch(sw));
                    break;
                }
            }
        }

        private IEnumerator AliceActivateSwitch(GameObject sw)
        {
            if (aliceTransform == null) yield break;
            Vector3 target = sw.transform.position;
            // Move to switch
            while (Vector3.Distance(aliceTransform.position, target) > 0.3f)
            {
                aliceTransform.position = Vector3.MoveTowards(
                    aliceTransform.position, target, aliceMoveSpeed * Time.deltaTime);
                yield return null;
            }
            // Activate
            var pc = sw.GetComponent<PuzzleSwitch>();
            if (pc != null) pc.Activate();
            AliceScore += 100;
            AliceSay("got one!");
        }

        // ── Racing Duo ──

        private void InitRacingDuo()
        {
            // Create checkpoints around the room
            for (int i = 0; i < 8; i++)
            {
                float angle = (i / 8f) * Mathf.PI * 2f;
                Vector3 pos = GetRoomCenter() + new Vector3(Mathf.Cos(angle) * 3f, 0.5f, Mathf.Sin(angle) * 3f);
                var cp = CreateCheckpoint(pos, i);
                _treasures.Add(cp);
            }
            AliceSay("first to all checkpoints wins. ready... go!");
        }

        private void UpdateRacingDuo()
        {
            // Alice races to checkpoints
            // Simple: go to nearest unvisited checkpoint
            GameObject nearest = null;
            float nearestDist = float.MaxValue;
            foreach (var cp in _treasures)
            {
                if (cp == null) continue;
                var rc = cp.GetComponent<RaceCheckpoint>();
                if (rc != null && !rc.aliceVisited)
                {
                    float d = Vector3.Distance(cp.transform.position, aliceTransform.position);
                    if (d < nearestDist) { nearestDist = d; nearest = cp; }
                }
            }

            if (nearest != null && aliceTransform != null)
            {
                aliceTransform.position = Vector3.MoveTowards(
                    aliceTransform.position, nearest.transform.position, aliceMoveSpeed * 1.5f * Time.deltaTime);
                Vector3 dir = (nearest.transform.position - aliceTransform.position).normalized;
                if (dir != Vector3.zero)
                    aliceTransform.rotation = Quaternion.Slerp(aliceTransform.rotation,
                        Quaternion.LookRotation(dir), Time.deltaTime * 5f);

                if (nearestDist < 0.3f)
                {
                    var rc = nearest.GetComponent<RaceCheckpoint>();
                    if (rc != null) { rc.aliceVisited = true; AliceScore += 50; }
                }
            }

            // Check if Alice finished
            bool allVisited = true;
            foreach (var cp in _treasures)
            {
                if (cp == null) continue;
                var rc = cp.GetComponent<RaceCheckpoint>();
                if (rc != null && !rc.aliceVisited) { allVisited = false; break; }
            }
            if (allVisited && _gameTimer > 3f)
            {
                AliceSay("i win! rematch?");
                StopGame();
            }
        }

        // ── Defense Duo ──

        private IEnumerator InitDefenseDuo()
        {
            // Create a core to protect
            _playerCore = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            _playerCore.transform.position = GetRoomCenter();
            _playerCore.transform.localScale = Vector3.one * 0.3f;
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.2f, 0.8f, 0.3f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.1f, 0.5f, 0.2f) * 2f);
            _playerCore.GetComponent<Renderer>().material = mat;
            _aliceWeapon = CreateWeapon(aliceRightHand ?? aliceTransform, new Color(0.3f, 0.8f, 1f));
            yield return new WaitForSeconds(0.5f);
            SpawnWave();
            AliceSay("protect the core. i've got the back.");
        }

        private void UpdateDefenseDuo()
        {
            UpdateCoopShooter();  // Reuse shooter AI

            // Check core health
            if (_playerCore != null)
            {
                var health = _playerCore.GetComponent<CoreHealth>();
                if (health != null && health.CurrentHealth <= 0)
                {
                    Defeat();
                }
            }
        }

        // ── Treasure Hunt ──

        private IEnumerator InitTreasureHunt()
        {
            // Hide treasures around the room
            for (int i = 0; i < 6; i++)
            {
                Vector3 pos = GetRoomCenter() + new Vector3(
                    Random.Range(-3f, 3f), Random.Range(0f, 1.5f), Random.Range(-3f, 3f));
                var treasure = CreateTreasure(pos);
                _treasures.Add(treasure);
            }
            yield return new WaitForSeconds(1f);
            AliceSay("i hid treasures. can you find them? i'll give hints.");
        }

        private void UpdateTreasureHunt()
        {
            // Alice gives hints based on proximity
            // Check player distance to each treasure
            if (Camera.main == null) return;
            Vector3 playerPos = Camera.main.transform.position;

            foreach (var t in _treasures)
            {
                if (t == null) continue;
                var tc = t.GetComponent<TreasureChest>();
                if (tc == null || tc.found) continue;

                float dist = Vector3.Distance(playerPos, t.transform.position);
                if (dist < 0.5f)
                {
                    tc.found = true;
                    PlayerScore += 100;
                    AliceSay("you found one!");
                }
                else if (dist < 1.5f && !tc.hintGiven)
                {
                    tc.hintGiven = true;
                    AliceSay("you're close... very close.");
                }
            }

            // Check all found
            bool allFound = true;
            foreach (var t in _treasures)
            {
                if (t == null) continue;
                var tc = t.GetComponent<TreasureChest>();
                if (tc != null && !tc.found) { allFound = false; break; }
            }
            if (allFound && _gameTimer > 3f)
            {
                Victory();
            }
        }

        // ── Building Challenge ──

        private void InitBuildingChallenge()
        {
            AliceSay("let's build something together. you place, i'll help.");
        }

        private void UpdateBuildingChallenge()
        {
            // Alice places blocks to complement what the user builds
            // Simple: periodically place a block near the user's last position
            if (_commTimer > 8f && Camera.main != null)
            {
                Vector3 pos = Camera.main.transform.position + Camera.main.transform.forward * 1f;
                pos.y = 0.5f;
                var block = GameObject.CreatePrimitive(PrimitiveType.Cube);
                block.transform.position = pos;
                block.transform.localScale = Vector3.one * 0.2f;
                var mat = new Material(Shader.Find("Standard"));
                mat.color = Color.HSVToRGB(Random.value, 0.7f, 0.9f);
                block.GetComponent<Renderer>().material = mat;
                _treasures.Add(block);
                AliceScore += 10;
                AliceSay("placed one there.");
            }
        }

        // ── Combat Helpers ──

        private void ShootAt(GameObject target, float accuracy)
        {
            if (aliceRightHand == null || target == null) return;

            // Create projectile
            var proj = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            proj.transform.position = aliceRightHand.position;
            proj.transform.localScale = Vector3.one * 0.05f;
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.3f, 0.8f, 1f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.3f, 0.8f, 1f) * 2f);
            proj.GetComponent<Renderer>().material = mat;

            // Direction with accuracy offset
            Vector3 dir = (target.transform.position - proj.transform.position).normalized;
            if (Random.value > accuracy)
            {
                dir += Random.insideUnitSphere * 0.3f;
                dir.Normalize();
            }

            var rb = proj.AddComponent<Rigidbody>();
            rb.linearVelocity = dir * 10f;
            proj.AddComponent<Projectile>().target = target;
            _projectiles.Add(proj);
            Destroy(proj, 3f);
        }

        private Vector3 GetTacticalPosition(Vector3 enemyPos)
        {
            if (Camera.main == null) return aliceTransform.position;
            Vector3 playerPos = Camera.main.transform.position;
            // Alice positions herself to flank
            Vector3 toEnemy = (enemyPos - playerPos).normalized;
            Vector3 flank = Vector3.Cross(toEnemy, Vector3.up) * (aliceAggression > 0.5f ? 2f : -2f);
            return playerPos + flank + Vector3.back * 1f;
        }

        // ── Object Creators ──

        private GameObject CreateWeapon(Transform parent, Color color)
        {
            var go = new GameObject("AliceWeapon");
            go.transform.SetParent(parent, false);
            go.transform.localPosition = new Vector3(0, 0, 0.1f);

            var body = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.03f, 0.15f, 0.03f);
            body.transform.localRotation = Quaternion.Euler(90, 0, 0);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = color;
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", color * 0.5f);
            body.GetComponent<Renderer>().material = mat;

            return go;
        }

        private GameObject CreateEnemy(Vector3 pos)
        {
            var go = new GameObject("Enemy");
            go.transform.position = pos;
            var body = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.3f, 0.5f, 0.3f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.8f, 0.1f, 0.1f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.5f, 0.05f, 0.05f) * 2f);
            body.GetComponent<Renderer>().material = mat;

            // Move toward player
            var mover = go.AddComponent<EnemyMover>();
            mover.speed = 0.8f;
            mover.health = 100;

            // Collider
            var col = go.AddComponent<SphereCollider>();
            col.radius = 0.4f;

            return go;
        }

        private GameObject CreatePuzzleSwitch(Vector3 pos, int index)
        {
            var go = new GameObject($"Switch_{index}");
            go.transform.position = pos;
            var body = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.2f, 0.05f, 0.2f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.5f, 0.5f, 0.5f);
            body.GetComponent<Renderer>().material = mat;

            var pc = go.AddComponent<PuzzleSwitch>();
            pc.index = index;

            return go;
        }

        private GameObject CreateCheckpoint(Vector3 pos, int index)
        {
            var go = new GameObject($"Checkpoint_{index}");
            go.transform.position = pos;
            var ring = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            ring.transform.SetParent(go.transform, false);
            ring.transform.localScale = Vector3.one * 0.3f;
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(1f, 0.8f, 0.2f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(1f, 0.8f, 0.2f) * 2f);
            ring.GetComponent<Renderer>().material = mat;

            go.AddComponent<RaceCheckpoint>().index = index;
            return go;
        }

        private GameObject CreateTreasure(Vector3 pos)
        {
            var go = new GameObject("Treasure");
            go.transform.position = pos;
            var body = GameObject.CreatePrimitive(PrimitiveType.Cube);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.2f, 0.15f, 0.2f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(1f, 0.7f, 0.1f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(1f, 0.7f, 0.1f) * 1.5f);
            body.GetComponent<Renderer>().material = mat;
            go.AddComponent<TreasureChest>();
            return go;
        }

        // ── Victory / Defeat ──

        private void Victory()
        {
            AliceSay(VictoryLines[Random.Range(0, VictoryLines.Length)]);
            IsPlaying = false;
        }

        private void Defeat()
        {
            AliceSay(DefeatLines[Random.Range(0, DefeatLines.Length)]);
            IsPlaying = false;
        }

        // ── Communication ──

        private void AliceSay(string text)
        {
            Debug.Log($"[CoOp] Alice: {text}");
            if (wsClient != null)
            {
                var payload = new CoopCommPayload
                {
                    type = "coop.comm",
                    text = text,
                    mode = CurrentMode.ToString(),
                    playerScore = PlayerScore,
                    aliceScore = AliceScore,
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        [System.Serializable]
        private class CoopCommPayload
        {
            public string type;
            public string text;
            public string mode;
            public int playerScore;
            public int aliceScore;
        }

        // ── Helpers ──

        private Vector3 GetRoomCenter()
        {
            return Camera.main != null
                ? Camera.main.transform.position - Camera.main.transform.forward * 0.5f
                : Vector3.zero;
        }

        private Vector3 GetSpawnPositionAroundPlayer(float radius)
        {
            float angle = Random.Range(0f, Mathf.PI * 2f);
            Vector3 center = GetRoomCenter();
            return center + new Vector3(Mathf.Cos(angle) * radius, 0, Mathf.Sin(angle) * radius);
        }

        // ── Public API ──

        public void AliceStartGame(string modeName)
        {
            if (System.Enum.TryParse<CoopGameMode>(modeName, true, out var mode))
                StartGame(mode);
        }

        public void PlayerScored(int points)
        {
            PlayerScore += points;
            if (Random.value < 0.3f)
                AliceSay("nice!");
        }
    }

    // ── Helper Components ──

    public class EnemyMover : MonoBehaviour
    {
        public float speed = 0.8f;
        public int health = 100;

        private void Update()
        {
            if (Camera.main == null) return;
            Vector3 target = Camera.main.transform.position;
            target.y = transform.position.y;
            transform.position = Vector3.MoveTowards(transform.position, target, speed * Time.deltaTime);
            transform.LookAt(target);
        }

        private void OnTriggerEnter(Collider other)
        {
            var proj = other.GetComponent<Projectile>();
            if (proj != null)
            {
                health -= 50;
                if (health <= 0) Destroy(gameObject);
            }
        }
    }

    public class Projectile : MonoBehaviour
    {
        public GameObject target;
    }

    public class PuzzleSwitch : MonoBehaviour
    {
        public int index;
        public bool activated;
        public bool aliceActivating;
        private Renderer _rend;
        private Material _mat;

        private void Awake()
        {
            _rend = GetComponentInChildren<Renderer>();
            _mat = _rend.material;
        }

        public void Activate()
        {
            activated = true;
            if (_mat != null)
            {
                _mat.color = new Color(0.2f, 0.9f, 0.3f);
                _mat.EnableKeyword("_EMISSION");
                _mat.SetColor("_EmissionColor", new Color(0.2f, 0.9f, 0.3f) * 2f);
            }
        }
    }

    public class RaceCheckpoint : MonoBehaviour
    {
        public int index;
        public bool aliceVisited;
        public bool playerVisited;
    }

    public class TreasureChest : MonoBehaviour
    {
        public bool found;
        public bool hintGiven;
    }

    public class CoreHealth : MonoBehaviour
    {
        public int maxHealth = 100;
        public int CurrentHealth { get; private set; }

        private void Awake() { CurrentHealth = maxHealth; }

        public void TakeDamage(int amount)
        {
            CurrentHealth = Mathf.Max(0, CurrentHealth - amount);
        }
    }
}
