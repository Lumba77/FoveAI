// ── behavior_config.js — Avatar behavior tuning (hot-reloadable) ─────────────
// Tweak Alice's personality, gaze, gestures, and timing in real-time.
//
// These params are read by MovementEngine and other behavior scripts.
// Edit, save, and Alice's behavior changes immediately.

// ── Autonomous household presence ──
// When true, Jen has gentle autonomous behavior (wandering, looking around,
// micro-gestures) when the LLM hasn't sent a movement command recently.
// This makes her feel like a natural part of the household.
FoveAI.setParam("avatar.autonomousMode", true);

// ── "Be Jen" First-Person POV ──
// When true, the render camera follows Jen's head bone so you experience
// the world through her eyes. Toggle with the V key or this param.
FoveAI.setParam("avatar.jenPOV", false);

// ── Gaze ──
FoveAI.setParam("avatar.gazeAtUserProbability", 0.7);  // 70% look at user
FoveAI.setParam("avatar.gazeHoldDuration.min", 2.0);   // seconds
FoveAI.setParam("avatar.gazeHoldDuration.max", 6.0);
FoveAI.setParam("avatar.gazeLerpSpeed", 6.0);

// ── Movement ──
FoveAI.setParam("avatar.walkSpeed", 1.0);
FoveAI.setParam("avatar.turnSpeed", 2.0);
FoveAI.setParam("avatar.maxWanderDistance", 3.0);
FoveAI.setParam("avatar.preferredStepDistance", 0.8);
FoveAI.setParam("avatar.approachDistance", 1.2);

// ── Decision timing ──
FoveAI.setParam("avatar.decisionInterval", 4.0);       // seconds between autonomous decisions
FoveAI.setParam("avatar.minStateDuration", 3.0);
FoveAI.setParam("avatar.returnHomeDelay", 8.0);

// ── Drives (Alice's internal motivations) ──
FoveAI.setParam("avatar.curiosity", 0.3);
FoveAI.setParam("avatar.restlessness", 0.1);
FoveAI.setParam("avatar.socialNeed", 0.5);
FoveAI.setParam("avatar.energy", 1.0);
FoveAI.setParam("avatar.expressiveness", 0.5);

// ── Gesture probabilities ──
FoveAI.setParam("avatar.idleMicroGestureChance", 0.3);
FoveAI.setParam("avatar.spontaneity", 0.05);

// ── 4-State cycle ──
FoveAI.setParam("avatar.fourStateCycleInterval", 30.0); // seconds per mood cycle
FoveAI.setParam("avatar.dreamStateInterval", 8.0);

// ── Conversation ──
FoveAI.setParam("avatar.microIdleTimeout", 12.0);       // seconds before IDLE → MICRO_IDLE

// ── Emotion decay ──
FoveAI.setParam("avatar.emotionDecayTime", 5.0);        // seconds for emotion to fade

// ── Breathing ──
FoveAI.setParam("avatar.breathRate", 0.001);
FoveAI.setParam("avatar.idleSwayAmount", 0.02);

FoveAI.log("behavior_config loaded — Alice's personality tuned");
