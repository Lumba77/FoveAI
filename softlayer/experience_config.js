// ── experience_config.js — Experience parameters (hot-reloadable) ────────────
// Controls the Director, Seasonal Theming, Virtual Touring, and other
// experiences. Edit and save to change the VR environment in real-time.

// ── Seasonal Theming ──
// Sterile default: dressing is opt-in — the Director or the user can apply a
// season on demand, but nothing decorates the scene at boot.
FoveAI.setParam("season.autoDetect", false);
FoveAI.setParam("season.current", "autumn");           // override: "spring"|"summer"|"autumn"|"winter"
FoveAI.setParam("season.particleDensity", 1.0);
FoveAI.setParam("season.commentInterval", 300);        // seconds between seasonal comments

// ── Holiday overlay ──
FoveAI.setParam("holiday.autoDetect", false);
FoveAI.setParam("holiday.current", "none");            // "none"|"christmas"|"halloween"|"newyear"|"valentine"|"easter"

// ── Director Engine ──
FoveAI.setParam("director.enabled", true);
FoveAI.setParam("director.suspenseChance", 0.15);      // 15% chance of suspense event
FoveAI.setParam("director.eventInterval", 180);        // seconds between director events
FoveAI.setParam("director.genre", "slice_of_life");    // "slice_of_life"|"adventure"|"mystery"|"cozy"

// ── Director Voice (spooky Leonard Cohen-style narrator) ──
// The Director's narrator speaks with pitch=0 (lowest), rate=0.65 (slow, soft),
// routed through a low-pass filter at 600Hz and an 8-second "Mount Zion" reverb
// — a vast, dark, sacred-stone cathedral tail. Soft but dark, reverberated.
FoveAI.setParam("director.voicePitch", 0);             // 0=lowest, 2=highest
FoveAI.setParam("director.voiceRate", 0.65);           // slow, deliberate, soft
FoveAI.setParam("director.voiceVolume", 0.7);          // softer — let the reverb breathe
FoveAI.setParam("director.reverbAmount", 0.65);        // wet — the reverb IS the character
FoveAI.setParam("director.filterCutoff", 600);         // Hz — dark, soft, no harsh highs

// ── Avalanche Dark Ambient Music ──
// Procedural slow minor chord progression (Am-F-G-Am) inspired by
// Leonard Cohen's "Avalanche". Plays in the room during Director events
// or when toggled manually. Press M in the XR Vessel to toggle.
FoveAI.setParam("director.avalancheMusic", false);     // true = start playing
FoveAI.setParam("director.avalancheVolume", 0.15);     // 0=silent, 1=loud

// ── Codec2-style Radio Effect (FreeDV) ──
// Adds radio squelch bursts + static bed around the Director's voice,
// simulating a low-bitrate digital HF radio transmission (FreeDV/Codec2).
// The Director sounds like he's speaking through an old radio from beyond.
FoveAI.setParam("director.radioEffect", true);         // true = radio quality on
FoveAI.setParam("director.radioIntensity", 0.7);       // 0=clean, 1=heavy static

// ── Ambient audio ──
FoveAI.setParam("audio.ambientVolume", 0.3);
FoveAI.setParam("audio.droneVolume", 0.15);
FoveAI.setParam("audio.stingVolume", 0.4);

// ── Virtual Touring ──
FoveAI.setParam("tour.enabled", false);
FoveAI.setParam("tour.destination", "RainyCafe");      // see WebcamWindowGazing presets
FoveAI.setParam("tour.autoCycle", false);
FoveAI.setParam("tour.cycleInterval", 600);            // seconds

// ── Webcam Window ──
FoveAI.setParam("webcam.enabled", false);
FoveAI.setParam("webcam.location", "LocalDesk");       // "LocalDesk"|"TimesSquare"|"SwissAlps" etc.
FoveAI.setParam("webcam.refreshInterval", 30);         // seconds
FoveAI.setParam("webcam.aliceGazeInterval", 12);       // seconds between Alice looking
FoveAI.setParam("webcam.commentChance", 0.5);

// ── Live Webcam Plaster ──
// Projects the rigged room webcam as a live video texture onto the scanned
// room walls, giving the avatar an extra view of the environment.
// The webcam is rigged in portrait mode (vertical), so the texture is
// rotated 90° to map correctly onto wall surfaces.
FoveAI.setParam("webcamPlaster.enabled", true);
FoveAI.setParam("webcamPlaster.orientation", "portrait");  // "portrait"|"landscape"
FoveAI.setParam("webcamPlaster.opacity", 0.85);            // 0.0 = invisible, 1.0 = opaque
FoveAI.setParam("webcamPlaster.surfaces", "wall,screen");  // which surface types to plaster onto

// ── Lighting ──
FoveAI.setParam("lighting.ambientIntensity", 0.6);
FoveAI.setParam("lighting.keyLightIntensity", 0.8);
FoveAI.setParam("lighting.keyLightColor", [1.0, 0.95, 0.9]);  // warm white
FoveAI.setParam("lighting.fillLightIntensity", 0.3);
FoveAI.setParam("lighting.fillLightColor", [0.5, 0.7, 1.0]);  // cool blue

// ── Particle effects ──
FoveAI.setParam("particles.snow.enabled", false);
FoveAI.setParam("particles.snow.density", 0.5);
FoveAI.setParam("particles.rain.enabled", false);
FoveAI.setParam("particles.rain.density", 0.3);
FoveAI.setParam("particles.leaves.enabled", true);     // autumn default
FoveAI.setParam("particles.leaves.density", 0.4);

// ── Weather (from local_webcam.py weather streamer) ──
FoveAI.setParam("weather.city", "Stockholm");
FoveAI.setParam("weather.updateInterval", 600);        // 10 minutes
FoveAI.setParam("weather.driveSeason", true);          // auto-set season from weather

FoveAI.log("experience_config loaded — environment configured: autumn, cozy, LocalDesk webcam ready");
