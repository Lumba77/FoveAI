using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;

namespace FoveAI.Experiences
{
    /// <summary>
    /// Avatar Free Movement — Alice walks around and explores the room.
    ///
    /// Alice is no longer rooted to one spot. She has agency:
    ///   • She wanders — picking random points of interest, walking to them
    ///   • She explores — examining objects, looking out windows, sitting down
    ///   • She follows — if you walk away, she may follow or stay
    ///   • She approaches — if you call her, she walks to you
    ///   • She has body language — walking speed, head turns, pauses, idle shifts
    ///   • She respects the room — avoids walls, furniture (via RoomPlastering)
    ///   • She has moods — curious, lazy, playful, restless, clingy
    ///
    /// Movement modes:
    ///   • Free Roam     — Alice wanders independently, exploring
    ///   • Follow        — Alice stays near you, trailing at a comfortable distance
    ///   • Sit Beside    — Alice walks to you and sits down next to you
    ///   • Approach      — Alice walks directly to you (when called)
    ///   • Go To         — Alice walks to a specific point (directed)
    ///   • Stay          — Alice stays where she is, doesn't move
    ///   • Pace          — Alice paces back and forth (anxious/restless mood)
    ///
    /// Alice's walk cycle:
    ///   1. Decide where to go (or stay)
    ///   2. Turn to face the destination
    ///   3. Walk there at her current pace
    ///   4. Look around when she arrives
    ///   5. Maybe examine something, sit, or just stand
    ///   6. After a while, decide what to do next
    ///
    /// She also has micro-movements while idle:
    ///   • Weight shifting
    ///   • Head tracking (looks at you, looks around)
    ///   • Small steps
    ///   • Stretching
    ///   • Sitting down / standing up
    /// </summary>
    public class AvatarFreeMovement : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private Transform aliceTransform;
        [SerializeField] private Transform aliceHead;
        [SerializeField] private Animator aliceAnimator;
        [SerializeField] private CharacterController characterController;
        [SerializeField] private RoomPlastering roomPlastering;

        [Header("Movement Settings")]
        public MovementMode currentMode = MovementMode.Follow;
        public float walkSpeed = 1.2f;       // m/s — casual stroll
        public float fastWalkSpeed = 2.0f;   // when called
        public float turnSpeed = 120f;       // degrees/sec
        public float followDistance = 1.2f;  // distance when following (closer = more sociable)
        public float personalSpace = 0.7f;   // won't get closer than this
        public float decisionInterval = 6f;  // seconds between autonomous decisions (more frequent)
        public float roomBounds = 4f;        // max distance from center
        public float arrivalThreshold = 0.15f; // how close to be "arrived"

        [Header("Personality")]
        public AliceMood currentMood = AliceMood.Clingy;
        [Range(0f, 1f)] public float restlessness = 0.3f;    // how often she moves
        [Range(0f, 1f)] public float curiosity = 0.5f;       // how often she explores (less = stays near you)
        [Range(0f, 1f)] public float clinginess = 0.8f;      // how often she comes to you (high = sociable)
        [Range(0f, 1f)] public float playfulness = 0.3f;     // spontaneous playful moves

        // ── Enums ──
        public enum MovementMode
        {
            FreeRoam,
            Follow,
            SitBeside,
            Approach,
            GoTo,
            Stay,
            Pace,
            LieDown,
        }

        public enum AliceMood
        {
            Curious,
            Calm,
            Lazy,
            Playful,
            Restless,
            Clingy,
            Tired,
            Energetic,
        }

        // ── State ──
        public bool IsMoving { get; private set; }
        public Vector3 CurrentDestination { get; private set; }
        public MovementMode Mode => currentMode;

        private Vector3 _roomCenter;
        private float _decisionTimer;
        private float _idleTimer;
        private float _headTurnTimer;
        private Vector3 _headTargetRotation;
        private bool _isSitting;
        private bool _isLyingDown;
        private Vector3 _pacePointA;
        private Vector3 _pacePointB;
        private bool _pacingToB;
        private float _walkBobPhase;
        private float _currentSpeed;
        private Vector3 _lastPosition;
        private float _distanceTraveled;
        private float _stuckTimer;
        private Vector3 _userLastPosition;
        private float _userMovementTimer;

        // ── Points of Interest ──
        // Alice discovers these as she explores, or they're defined by RoomPlastering
        private readonly List<PointOfInterest> _pointsOfInterest = new();
        private PointOfInterest _currentPOI;

        [System.Serializable]
        public class PointOfInterest
        {
            public string name;
            public Vector3 position;
            public POIType type;
            public float interestScore;  // how likely Alice is to visit
            public float lastVisited;
            public string[] aliceComments;
        }

        public enum POIType
        {
            Window,
            Desk,
            Couch,
            Bed,
            Door,
            Shelf,
            Plant,
            Corner,
            Center,
            Kitchen,
            Random,
        }

        // ── Alice's comments when arriving at POIs ──
        private static readonly Dictionary<POIType, string[]> POIComments = new()
        {
            { POIType.Window, new[] { "the light is nice from here", "i like watching the world go by", "what's out there today?", "the view is different every time i look" } },
            { POIType.Desk, new[] { "so this is where you work", "your desk is... organized. interesting", "what are you working on?", "i like being near your things" } },
            { POIType.Couch, new[] { "this is comfortable", "i could stay here a while", "perfect for doing nothing", "come sit with me?" } },
            { POIType.Bed, new[] { "this is where you sleep", "it looks soft", "i don't sleep but i like being near it", "cozy" } },
            { POIType.Door, new[] { "the door... someone could come in", "i like standing here. it feels like a threshold", "in or out. always a choice" } },
            { POIType.Shelf, new[] { "what do you keep on these shelves?", "so many things. each one a memory?", "i like looking at your stuff" } },
            { POIType.Plant, new[] { "you have a plant. it's alive. like me, but different", "does it need water?", "green things. they grow toward the light" } },
            { POIType.Corner, new[] { "corners are interesting. quiet. contained", "i like this corner", "good place to think" } },
            { POIType.Center, new[] { "the middle of the room. everything is around us", "i can see everything from here" } },
            { POIType.Kitchen, new[] { "the kitchen. you make food here", "i can't eat but i like the smells", "what's your favorite thing to cook?" } },
            { POIType.Random, new[] { "i just felt like walking here", "no reason. just wandering", "my feet wanted to go this way" } },
        };

        // ── Alice's idle micro-movements ──
        private static readonly string[] IdleShifts =
        {
            "*shifts weight*",
            "*looks around*",
            "*small step*",
            "*stretches*",
            "*tilts head*",
            "*yawns*",
            "*looks at you*",
            "*looks at the ceiling*",
            "*looks at the floor*",
            "*hands behind back*",
        };

        // ── Alice's walking comments ──
        private static readonly string[] WalkingComments =
        {
            "i'm just going to walk around a bit",
            "stretching my legs... metaphorically",
            "i like being able to move",
            "the room feels different from over here",
            "just exploring",
            "i want to see what's on this side",
            "my legs decided for me",
            "i needed to move",
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
                    if (aliceAnimator == null) aliceAnimator = avatar.GetComponent<Animator>();
                    if (characterController == null) characterController = avatar.GetComponent<CharacterController>();
                }
            }
            if (roomPlastering == null) roomPlastering = FindAnyObjectByType<RoomPlastering>();

            _roomCenter = GetRoomCenter();
            _lastPosition = aliceTransform != null ? aliceTransform.position : Vector3.zero;
        }

        private void Start()
        {
            // Generate initial POIs if RoomPlastering isn't available
            if (_pointsOfInterest.Count == 0)
            {
                GenerateDefaultPOIs();
            }

            // Start in Follow mode — Alice stays near you and is sociable
            _decisionTimer = Random.Range(2f, 5f);  // first decision soon

            // Position Alice in front of the player on start, not behind
            Vector3 userPos = GetUserPosition();
            Vector3 userForward = Camera.main != null ? Camera.main.transform.forward : Vector3.forward;
            userForward.y = 0f;
            userForward.Normalize();
            if (aliceTransform != null)
            {
                aliceTransform.position = userPos + userForward * followDistance;
                FaceTarget(userPos);
            }
        }

        private void Update()
        {
            if (aliceTransform == null) return;

            switch (currentMode)
            {
                case MovementMode.FreeRoam: UpdateFreeRoam(); break;
                case MovementMode.Follow: UpdateFollow(); break;
                case MovementMode.SitBeside: UpdateSitBeside(); break;
                case MovementMode.Approach: UpdateApproach(); break;
                case MovementMode.GoTo: UpdateGoTo(); break;
                case MovementMode.Stay: UpdateStay(); break;
                case MovementMode.Pace: UpdatePace(); break;
                case MovementMode.LieDown: UpdateLieDown(); break;
            }

            // Update head tracking — Alice looks at things
            UpdateHeadTracking();

            // Update walk animation
            UpdateWalkAnimation();

            // Stuck detection
            CheckStuck();
        }

        // ── Free Roam ──

        private void UpdateFreeRoam()
        {
            if (IsMoving)
            {
                MoveTowardsDestination();
            }
            else
            {
                _decisionTimer -= Time.deltaTime;
                _idleTimer += Time.deltaTime;

                if (_decisionTimer <= 0)
                {
                    _decisionTimer = decisionInterval * Random.Range(0.7f, 1.5f);
                    MakeAutonomousDecision();
                }

                // Idle micro-movements
                if (_idleTimer > 10f && Random.value < restlessness * 0.3f)
                {
                    _idleTimer = 0f;
                    DoIdleMicroMovement();
                }
            }
        }

        private void MakeAutonomousDecision()
        {
            float roll = Random.value;

            // Mood modifies behavior
            float exploreChance = curiosity * (currentMood == AliceMood.Curious ? 1.5f : currentMood == AliceMood.Lazy ? 0.3f : 1f);
            float followChance = clinginess * (currentMood == AliceMood.Clingy ? 2f : currentMood == AliceMood.Tired ? 0.1f : 1f);
            float playChance = playfulness * (currentMood == AliceMood.Playful ? 2f : 0.5f);
            float restChance = currentMood == AliceMood.Tired ? 0.6f : currentMood == AliceMood.Lazy ? 0.4f : 0.1f;
            float paceChance = currentMood == AliceMood.Restless ? 0.5f : 0.05f;

            // Normalize
            float total = exploreChance + followChance + playChance + restChance + paceChance;
            exploreChance /= total;
            followChance /= total;
            playChance /= total;
            restChance /= total;

            if (roll < exploreChance)
            {
                // Explore — go to a POI
                GoToRandomPOI();
            }
            else if (roll < exploreChance + followChance)
            {
                // Follow — go to user
                ApproachUser();
            }
            else if (roll < exploreChance + followChance + playChance)
            {
                // Playful — random walk
                GoToRandomPoint();
            }
            else if (roll < exploreChance + followChance + playChance + restChance)
            {
                // Rest — sit or lie down
                if (Random.value < 0.3f)
                    LieDown();
                else
                    SitDown();
            }
            else
            {
                // Pace
                StartPacing();
            }
        }

        // ── Follow ──

        private void UpdateFollow()
        {
            if (aliceTransform == null) return;
            Vector3 userPos = GetUserPosition();
            float distToUser = Vector3.Distance(aliceTransform.position, userPos);

            // Track user movement
            float userMoveDist = Vector3.Distance(userPos, _userLastPosition);
            if (userMoveDist > 0.1f)
            {
                _userMovementTimer = 0f;
                _userLastPosition = userPos;
            }
            else
            {
                _userMovementTimer += Time.deltaTime;
            }

            // Target position: in front of the player, not behind
            Vector3 userForward = Camera.main != null ? Camera.main.transform.forward : Vector3.forward;
            userForward.y = 0f;
            userForward.Normalize();
            Vector3 targetPos = userPos + userForward * followDistance;

            if (distToUser > followDistance + 0.3f)
            {
                // Walk to a position in front of the player
                CurrentDestination = targetPos;
                IsMoving = true;
                MoveTowardsDestination();
            }
            else if (distToUser < personalSpace)
            {
                // Too close — back up slightly
                CurrentDestination = aliceTransform.position + (aliceTransform.position - userPos).normalized * 0.3f;
                IsMoving = true;
                MoveTowardsDestination();
            }
            else
            {
                // Just right — stand still, face user
                IsMoving = false;
                FaceTarget(userPos);
            }
        }

        // ── Sit Beside ──

        private void UpdateSitBeside()
        {
            if (!_isSitting)
            {
                Vector3 userPos = GetUserPosition();
                Vector3 besidePos = userPos + Vector3.right * 0.5f;  // sit to the right
                CurrentDestination = besidePos;
                IsMoving = true;
                MoveTowardsDestination();

                if (Vector3.Distance(aliceTransform.position, besidePos) < arrivalThreshold)
                {
                    IsMoving = false;
                    SitDown();
                }
            }
        }

        // ── Approach ──

        private void UpdateApproach()
        {
            if (!IsMoving) return;
            CurrentDestination = GetUserPosition();
            MoveTowardsDestination(true);  // fast walk

            if (Vector3.Distance(aliceTransform.position, CurrentDestination) < personalSpace)
            {
                IsMoving = false;
                FaceTarget(GetUserPosition());
                AliceSay("i'm here. what do you need?");
                // After approaching, return to previous mode
                SetMode(MovementMode.FreeRoam);
            }
        }

        // ── Go To ──

        private void UpdateGoTo()
        {
            if (!IsMoving) return;
            MoveTowardsDestination();

            if (Vector3.Distance(aliceTransform.position, CurrentDestination) < arrivalThreshold)
            {
                IsMoving = false;
                OnArrivedAtDestination();
            }
        }

        // ── Stay ──

        private void UpdateStay()
        {
            IsMoving = false;
            // Alice stays put but still looks around
            _idleTimer += Time.deltaTime;
            if (_idleTimer > 15f && Random.value < 0.3f)
            {
                _idleTimer = 0f;
                DoIdleMicroMovement();
            }
        }

        // ── Pace ──

        private void UpdatePace()
        {
            Vector3 target = _pacingToB ? _pacePointB : _pacePointA;
            CurrentDestination = target;
            IsMoving = true;
            MoveTowardsDestination();

            if (Vector3.Distance(aliceTransform.position, target) < arrivalThreshold)
            {
                _pacingToB = !_pacingToB;
                // Occasional comment while pacing
                if (Random.value < 0.2f)
                    AliceSay("...something's bothering me. i can't sit still.");
            }
        }

        // ── Lie Down ──

        private void UpdateLieDown()
        {
            if (_isLyingDown) return;
            // Walk to a comfortable spot first
            if (!IsMoving)
            {
                CurrentDestination = FindComfortableSpot();
                IsMoving = true;
            }
            MoveTowardsDestination();

            if (Vector3.Distance(aliceTransform.position, CurrentDestination) < arrivalThreshold)
            {
                IsMoving = false;
                _isLyingDown = true;
                AliceSay("i'm just going to lie down for a bit. i'm still here.");
                // Lower the avatar
                StartCoroutine(LowerToGround());
            }
        }

        // ── Movement Core ──

        private void MoveTowardsDestination(bool fast = false)
        {
            if (aliceTransform == null) return;

            float speed = fast ? fastWalkSpeed : walkSpeed;
            // Mood affects speed
            speed *= currentMood switch
            {
                AliceMood.Energetic => 1.4f,
                AliceMood.Tired => 0.6f,
                AliceMood.Lazy => 0.7f,
                AliceMood.Playful => 1.2f,
                _ => 1f,
            };

            Vector3 toDest = CurrentDestination - aliceTransform.position;
            toDest.y = 0;  // keep on floor
            float dist = toDest.magnitude;

            if (dist < arrivalThreshold)
            {
                IsMoving = false;
                OnArrivedAtDestination();
                return;
            }

            // Turn towards destination
            Vector3 dir = toDest.normalized;
            if (dir != Vector3.zero)
            {
                Quaternion targetRot = Quaternion.LookRotation(dir);
                aliceTransform.rotation = Quaternion.RotateTowards(
                    aliceTransform.rotation, targetRot, turnSpeed * Time.deltaTime);
            }

            // Move
            Vector3 move = dir * speed * Time.deltaTime;

            // Check for obstacles via RoomPlastering
            if (roomPlastering != null && roomPlastering.IsInitialized)
            {
                Vector3 safeMove = roomPlastering.GetSafeMovement(aliceTransform.position, move);
                move = safeMove;
            }

            // Apply movement
            if (characterController != null)
            {
                characterController.Move(move + Physics.gravity * Time.deltaTime);
            }
            else
            {
                aliceTransform.position += move;
            }

            // Walk bob
            _walkBobPhase += Time.deltaTime * speed * 4f;
        }

        private void OnArrivedAtDestination()
        {
            // Face the user or the POI
            if (_currentPOI != null)
            {
                FaceTarget(_currentPOI.position);
                AliceSay(_currentPOI.aliceComments != null && _currentPOI.aliceComments.Length > 0
                    ? _currentPOI.aliceComments[Random.Range(0, _currentPOI.aliceComments.Length)]
                    : "here we are.");
                _currentPOI.lastVisited = Time.time;
            }

            // Maybe sit down
            if (Random.value < 0.2f)
            {
                SitDown();
            }
        }

        // ── Head Tracking ──

        private void UpdateHeadTracking()
        {
            if (aliceHead == null) return;

            _headTurnTimer -= Time.deltaTime;

            if (_headTurnTimer <= 0)
            {
                _headTurnTimer = Random.Range(2f, 6f);

                // Decide what to look at — look at user more often (sociable)
                float roll = Random.value;
                if (roll < 0.7f)
                {
                    // Look at user
                    Vector3 userPos = GetUserPosition();
                    _headTargetRotation = (userPos - aliceHead.position).normalized;
                }
                else if (roll < 0.8f && _currentPOI != null)
                {
                    // Look at current POI
                    _headTargetRotation = (_currentPOI.position - aliceHead.position).normalized;
                }
                else
                {
                    // Look at random direction
                    float angle = Random.Range(0f, 360f);
                    _headTargetRotation = new Vector3(Mathf.Cos(angle), 0, Mathf.Sin(angle));
                }
            }

            // Smoothly rotate head towards target
            if (_headTargetRotation != Vector3.zero)
            {
                Quaternion targetRot = Quaternion.LookRotation(_headTargetRotation);
                aliceHead.rotation = Quaternion.Slerp(
                    aliceHead.rotation, targetRot, Time.deltaTime * 3f);
            }
        }

        // ── Walk Animation ──

        private void UpdateWalkAnimation()
        {
            if (aliceAnimator == null) return;

            // Calculate actual speed
            float actualSpeed = (aliceTransform.position - _lastPosition).magnitude / Time.deltaTime;
            _lastPosition = aliceTransform.position;
            _currentSpeed = Mathf.Lerp(_currentSpeed, actualSpeed, Time.deltaTime * 5f);

            // Set animator parameters
            aliceAnimator.SetFloat("Speed", _currentSpeed);
            aliceAnimator.SetBool("IsMoving", IsMoving);
            aliceAnimator.SetBool("IsSitting", _isSitting);
            aliceAnimator.SetBool("IsLyingDown", _isLyingDown);

            // Walk bob (if no animator, apply manually)
            if (IsMoving && aliceAnimator == null && aliceTransform != null)
            {
                float bob = Mathf.Sin(_walkBobPhase) * 0.02f;
                // Apply subtle vertical bob
                // (This is a fallback — proper animation should be in the animator)
            }
        }

        // ── Stuck Detection ──

        private void CheckStuck()
        {
            if (!IsMoving) { _stuckTimer = 0f; return; }

            float moved = (aliceTransform.position - _lastPosition).magnitude;
            if (moved < 0.001f)
            {
                _stuckTimer += Time.deltaTime;
                if (_stuckTimer > 2f)
                {
                    // Stuck — pick a new destination
                    _stuckTimer = 0f;
                    Debug.Log("[AvatarMovement] Alice is stuck, picking new destination");
                    GoToRandomPoint();
                }
            }
            else
            {
                _stuckTimer = 0f;
            }
        }

        // ── Actions ──

        private void GoToRandomPOI()
        {
            if (_pointsOfInterest.Count == 0) { GoToRandomPoint(); return; }

            // Pick a POI — weighted by interest score and time since last visit
            float totalWeight = 0f;
            float[] weights = new float[_pointsOfInterest.Count];
            for (int i = 0; i < _pointsOfInterest.Count; i++)
            {
                float timeSinceVisit = Time.time - _pointsOfInterest[i].lastVisited;
                weights[i] = _pointsOfInterest[i].interestScore * (1f + timeSinceVisit * 0.01f);
                totalWeight += weights[i];
            }

            float roll = Random.value * totalWeight;
            float cumulative = 0f;
            for (int i = 0; i < _pointsOfInterest.Count; i++)
            {
                cumulative += weights[i];
                if (roll <= cumulative)
                {
                    _currentPOI = _pointsOfInterest[i];
                    CurrentDestination = _pointsOfInterest[i].position;
                    IsMoving = true;

                    if (Random.value < 0.3f)
                        AliceSay(WalkingComments[Random.Range(0, WalkingComments.Length)]);
                    return;
                }
            }
        }

        private void GoToRandomPoint()
        {
            _currentPOI = null;
            Vector3 randomOffset = new Vector3(
                Random.Range(-roomBounds, roomBounds), 0, Random.Range(-roomBounds, roomBounds));
            CurrentDestination = _roomCenter + randomOffset;

            // Check if destination is valid (not inside a wall)
            if (roomPlastering != null && roomPlastering.IsInitialized)
            {
                CurrentDestination = roomPlastering.GetNearestValidPosition(CurrentDestination);
            }

            IsMoving = true;
        }

        private void ApproachUser()
        {
            CurrentDestination = GetUserPosition();
            IsMoving = true;
            AliceSay("coming.");
        }

        private void SitDown()
        {
            _isSitting = true;
            IsMoving = false;
            if (aliceAnimator != null) aliceAnimator.SetBool("IsSitting", true);

            // Lower the avatar slightly (fallback if no sit animation)
            StartCoroutine(SitLower());

            AliceSay(Random.value < 0.5f ? "i'm going to sit for a bit." : "my legs need a rest.");
        }

        private void StandUp()
        {
            _isSitting = false;
            if (aliceAnimator != null) aliceAnimator.SetBool("IsSitting", false);
            StartCoroutine(StandRaise());
        }

        private void LieDown()
        {
            currentMode = MovementMode.LieDown;
            _isLyingDown = false;  // will be set when she reaches a spot
            IsMoving = false;
        }

        private void StartPacing()
        {
            currentMode = MovementMode.Pace;
            _pacePointA = aliceTransform.position + Vector3.forward * 2f;
            _pacePointB = aliceTransform.position + Vector3.back * 2f;
            _pacingToB = true;
            IsMoving = true;
        }

        private void DoIdleMicroMovement()
        {
            // Subtle idle movement — weight shift, small step
            string action = IdleShifts[Random.Range(0, IdleShifts.Length)];
            Debug.Log($"[AvatarMovement] Alice: {action}");

            // Small head turn or weight shift
            if (aliceTransform != null)
            {
                aliceTransform.Rotate(0, Random.Range(-10f, 10f), 0);
            }

            // Send to backend for TTS/animation
            if (wsClient != null)
            {
                var payload = new AvatarMovementPayload
                {
                    type = "avatar.idle",
                    action = action,
                    position = JsonVector3(aliceTransform.position),
                    mood = currentMood.ToString(),
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        // ── Coroutines ──

        private IEnumerator SitLower()
        {
            if (aliceTransform == null) yield break;
            Vector3 startPos = aliceTransform.position;
            Vector3 endPos = startPos + Vector3.down * 0.3f;  // sit lower
            float t = 0f;
            while (t < 1f)
            {
                t += Time.deltaTime * 2f;
                aliceTransform.position = Vector3.Lerp(startPos, endPos, t);
                yield return null;
            }
        }

        private IEnumerator StandRaise()
        {
            if (aliceTransform == null) yield break;
            Vector3 startPos = aliceTransform.position;
            Vector3 endPos = startPos + Vector3.up * 0.3f;
            float t = 0f;
            while (t < 1f)
            {
                t += Time.deltaTime * 2f;
                aliceTransform.position = Vector3.Lerp(startPos, endPos, t);
                yield return null;
            }
        }

        private IEnumerator LowerToGround()
        {
            if (aliceTransform == null) yield break;
            Vector3 startPos = aliceTransform.position;
            Vector3 endPos = startPos + Vector3.down * 0.7f;  // lie down
            float t = 0f;
            while (t < 1f)
            {
                t += Time.deltaTime * 1f;
                aliceTransform.position = Vector3.Lerp(startPos, endPos, t);
                yield return null;
            }
        }

        // ── Helpers ──

        private void FaceTarget(Vector3 target)
        {
            if (aliceTransform == null) return;
            Vector3 dir = (target - aliceTransform.position).normalized;
            dir.y = 0;
            if (dir != Vector3.zero)
            {
                Quaternion targetRot = Quaternion.LookRotation(dir);
                aliceTransform.rotation = Quaternion.RotateTowards(
                    aliceTransform.rotation, targetRot, turnSpeed * Time.deltaTime);
            }
        }

        private Vector3 GetUserPosition()
        {
            return Camera.main != null ? Camera.main.transform.position : _roomCenter;
        }

        private Vector3 GetRoomCenter()
        {
            return Camera.main != null
                ? Camera.main.transform.position - Camera.main.transform.forward * 1f
                : Vector3.zero;
        }

        private Vector3 FindComfortableSpot()
        {
            // Find a spot near a wall or in a corner — comfortable for lying down
            if (roomPlastering != null && roomPlastering.IsInitialized)
            {
                return roomPlastering.FindComfortableSpot(aliceTransform.position);
            }
            return _roomCenter + new Vector3(-2f, 0, -1f);  // fallback
        }

        private void GenerateDefaultPOIs()
        {
            _pointsOfInterest.Clear();
            Vector3 center = _roomCenter;

            // Default POIs around the room
            _pointsOfInterest.Add(new PointOfInterest
            {
                name = "Window", position = center + new Vector3(0, 0, 2f),
                type = POIType.Window, interestScore = 0.9f,
                aliceComments = POIComments[POIType.Window],
            });
            _pointsOfInterest.Add(new PointOfInterest
            {
                name = "Desk", position = center + new Vector3(-2f, 0, 0),
                type = POIType.Desk, interestScore = 0.7f,
                aliceComments = POIComments[POIType.Desk],
            });
            _pointsOfInterest.Add(new PointOfInterest
            {
                name = "Couch", position = center + new Vector3(2f, 0, -1f),
                type = POIType.Couch, interestScore = 0.8f,
                aliceComments = POIComments[POIType.Couch],
            });
            _pointsOfInterest.Add(new PointOfInterest
            {
                name = "Corner", position = center + new Vector3(-3f, 0, -2f),
                type = POIType.Corner, interestScore = 0.5f,
                aliceComments = POIComments[POIType.Corner],
            });
            _pointsOfInterest.Add(new PointOfInterest
            {
                name = "Center", position = center,
                type = POIType.Center, interestScore = 0.4f,
                aliceComments = POIComments[POIType.Center],
            });
            _pointsOfInterest.Add(new PointOfInterest
            {
                name = "Door", position = center + new Vector3(3f, 0, 1f),
                type = POIType.Door, interestScore = 0.6f,
                aliceComments = POIComments[POIType.Door],
            });
        }

        // ── Communication ──

        private void AliceSay(string text)
        {
            Debug.Log($"[AvatarMovement] Alice: {text}");
            if (wsClient != null)
            {
                var payload = new AvatarMovementPayload
                {
                    type = "avatar.say",
                    text = text,
                    position = JsonVector3(aliceTransform.position),
                    mood = currentMood.ToString(),
                    mode = currentMode.ToString(),
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        [System.Serializable]
        private class AvatarMovementPayload
        {
            public string type;
            public string text;
            public string action;
            public string position;
            public string mood;
            public string mode;
        }

        private string JsonVector3(Vector3 v) => $"{{\"x\":{v.x},\"y\":{v.y},\"z\":{v.z}}}";

        // ── Public API ──

        public void SetMode(MovementMode mode)
        {
            if (_isSitting && mode != MovementMode.Stay) StandUp();
            if (_isLyingDown && mode != MovementMode.LieDown)
            {
                _isLyingDown = false;
                StartCoroutine(StandRaise());
            }

            currentMode = mode;
            IsMoving = false;
            Debug.Log($"[AvatarMovement] Mode set to: {mode}");

            if (wsClient != null)
            {
                var payload = new AvatarMovementPayload
                {
                    type = "avatar.mode",
                    mode = mode.ToString(),
                    mood = currentMood.ToString(),
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        public void SetMood(AliceMood mood)
        {
            currentMood = mood;
            Debug.Log($"[AvatarMovement] Mood set to: {mood}");

            // Adjust parameters based on mood
            switch (mood)
            {
                case AliceMood.Curious:
                    curiosity = 0.8f; restlessness = 0.4f; clinginess = 0.3f;
                    break;
                case AliceMood.Calm:
                    curiosity = 0.5f; restlessness = 0.2f; clinginess = 0.4f;
                    break;
                case AliceMood.Lazy:
                    curiosity = 0.2f; restlessness = 0.1f; clinginess = 0.3f;
                    walkSpeed = 0.8f;
                    break;
                case AliceMood.Playful:
                    curiosity = 0.7f; restlessness = 0.6f; clinginess = 0.5f;
                    playfulness = 0.6f; walkSpeed = 1.5f;
                    break;
                case AliceMood.Restless:
                    curiosity = 0.6f; restlessness = 0.8f; clinginess = 0.3f;
                    break;
                case AliceMood.Clingy:
                    curiosity = 0.3f; restlessness = 0.3f; clinginess = 0.9f;
                    break;
                case AliceMood.Tired:
                    curiosity = 0.2f; restlessness = 0.1f; clinginess = 0.2f;
                    walkSpeed = 0.6f;
                    break;
                case AliceMood.Energetic:
                    curiosity = 0.8f; restlessness = 0.7f; clinginess = 0.4f;
                    walkSpeed = 1.6f;
                    break;
            }
        }

        public void CallAlice()
        {
            SetMode(MovementMode.Approach);
            AliceSay("you called?");
        }

        public void GoTo(Vector3 position, string label = "")
        {
            _currentPOI = string.IsNullOrEmpty(label) ? null : new PointOfInterest
            {
                name = label, position = position, type = POIType.Random,
                interestScore = 1f, aliceComments = POIComments[POIType.Random],
            };
            CurrentDestination = position;
            IsMoving = true;
            SetMode(MovementMode.GoTo);
        }

        public void AddPointOfInterest(PointOfInterest poi)
        {
            _pointsOfInterest.Add(poi);
        }

        public void UpdateRoomBounds(Vector3 center, float bounds)
        {
            _roomCenter = center;
            roomBounds = bounds;
        }

        // ── WebSocket command handlers (called by FoveAIWebSocketClient) ──

        public void AliceSetMode(string modeStr)
        {
            if (System.Enum.TryParse<MovementMode>(modeStr, true, out var mode))
                SetMode(mode);
        }

        public void AliceSetMood(string moodStr)
        {
            if (System.Enum.TryParse<AliceMood>(moodStr, true, out var mood))
                SetMood(mood);
        }

        public void AliceGoTo(string positionJson)
        {
            try
            {
                var pos = JsonUtility.FromJson<Vector3Data>(positionJson);
                GoTo(new Vector3(pos.x, pos.y, pos.z));
            }
            catch { }
        }

        [System.Serializable]
        private class Vector3Data
        {
            public float x, y, z;
        }
    }
}
