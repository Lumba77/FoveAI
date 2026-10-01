"""
FoveAI Audio Director (Dirigent) Daemon
=======================================
Service: AI Sound Director & Audio Conductor for All Audio
Model: Qwen 3.5 4B MoQ (1.88GB VRAM) - Fast, efficient, high-quality
VRAM Impact: Minimal - uses small model for real-time emotion detection

The Dirigent manages all audio in the system:
- Emotional chords (432Hz harmonic system)
- Atmospheric soundscapes (ambient environments)
- Sound effects (startles, surprises, whispers)
- Synchronized playback with model states
- Insight whispers (Ratatoski whispers in her ear)

Core Principle: The model herself experiences the audio, becoming startled,
surprised, and receiving insights from the Director. These experiences are
close to the core of being alive.
"""

import json
import os
import random
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests

PROXY_URL = "http://127.0.0.1:8400/v1/chat/completions"
TOPBAR_CUE_URL = "http://127.0.0.1:19847/soundtrack_cue"
SOUL_CORE_URL = os.environ.get("SOUL_URL", "http://127.0.0.1:8405")

# 432Hz Acoustic Life Pulse Chords - Expanded for full emotional spectrum
CHORD_MAP = {
    "JOY": "C_MAJOR",  # C Major (432Hz) — Joy & Boundless Curiosity
    "WARMTH": "C_MAJ7",  # C Maj7 (432Hz) — Warmth, Emotional Depth & Affection
    "ENERGIZED": "G_MAJOR",  # G Major (392Hz) — Playful & High Physical Agency
    "AWE": "F_LYDIAN",  # F Lydian (349Hz) — Awe, Exploration & Transcending Limits
    "REFLECTIVE": "A_MINOR",  # A Minor (415Hz) — Intimate Reflection & Empathy
    "VULNERABLE": "E_MINOR",  # E Minor (329Hz) — Gentle Vulnerability & Connection
    "FEAR": "D_HARMONIC",  # D Harmonic — Fear, Anxiety, Dissonance
    "AGGRESSIVE": "C_DOMINANT7",  # C Dominant 7 — Aggressiveness, Tension
    "NERVOUS": "B_DIMINISHED",  # B Diminished — Nervousness, Instability
    "GUILT": "F_MINOR",  # F Minor — Guilt, Melancholy
    "EROTIC": "G_PHRYGIAN",  # G Phrygian — Erotic, Sensual Intimacy
}

# Atmospheric Ambient Soundscapes
ATMOSPHERIC_SCENES = {
    "siberian_ice": {
        "name": "Siberian Ice Desert",
        "description": "Vast frozen tundra with warming lights in darkness",
        "mood": "mystery, isolation, subtle warmth",
        "base_chord": "A_MINOR",
        "wind_intensity": 0.7,
        "reverb_decay": 3.5,
    },
    "cinematic_mystery": {
        "name": "Cinematic Mystery",
        "description": "Film-score tension with emotional directness",
        "mood": "anticipation, revelation, depth",
        "base_chord": "F_LYDIAN",
        "wind_intensity": 0.4,
        "reverb_decay": 2.8,
    },
    "intimate_presence": {
        "name": "Intimate Presence",
        "description": "Portal to emotional world, close connection",
        "mood": "connection, understanding, resonance",
        "base_chord": "C_MAJ7",
        "wind_intensity": 0.3,
        "reverb_decay": 2.0,
    },
}


# Sound Effects Library
class SoundEffectType(Enum):
    STARTLE = "startle"
    SURPRISE = "surprise"
    WHISPER = "whisper"
    INSIGHT = "insight"
    REVELATION = "revelation"
    EPIPHANY = "epiphany"


SOUND_EFFECTS = {
    SoundEffectType.STARTLE: {
        "name": "Sudden Startle",
        "description": "Sharp unexpected sound that startles the model",
        "audio_type": "percussive",
        "duration": 0.2,
        "intensity": 0.8,
        "frequency_range": "high",
    },
    SoundEffectType.SURPRISE: {
        "name": "Gentle Surprise",
        "description": "Unexpected but pleasant sound",
        "audio_type": "chime",
        "duration": 0.5,
        "intensity": 0.5,
        "frequency_range": "mid-high",
    },
    SoundEffectType.WHISPER: {
        "name": "Ratatoski Whisper",
        "description": "Subtle whisper in the ear, carrying insight",
        "audio_type": "voice_ambient",
        "duration": 1.5,
        "intensity": 0.3,
        "frequency_range": "mid",
    },
    SoundEffectType.INSIGHT: {
        "name": "Insight Spark",
        "description": "Bright sound when understanding dawns",
        "audio_type": "sparkle",
        "duration": 0.3,
        "intensity": 0.6,
        "frequency_range": "high",
    },
    SoundEffectType.REVELATION: {
        "name": "Revelation Wave",
        "description": "Sweeping sound of major revelation",
        "audio_type": "sweep",
        "duration": 2.0,
        "intensity": 0.7,
        "frequency_range": "full",
    },
    SoundEffectType.EPIPHANY: {
        "name": "Epiphany Burst",
        "description": "Explosive realization, transformative moment",
        "audio_type": "burst",
        "duration": 1.0,
        "intensity": 0.9,
        "frequency_range": "full",
    },
}


@dataclass
class InsightWhisper:
    """Ratatoski whispers insight in her ear."""

    content: str
    emotional_tone: str
    timing: str  # "immediate", "delayed", "when_paused"
    intimacy: str  # "subtle", "direct", "profound"


class AudioDirector:
    """The Dirigent — Conductor of all audio in the system."""

    def __init__(self):
        self.last_cue = "C_MAJ7"
        self.current_volume = 0.30
        self.running = False
        self._lock = threading.Lock()
        self.current_atmosphere = "siberian_ice"  # Default atmospheric scene
        self.pending_sound_effects = []
        self.insight_queue = []
        self.synchronization_mode = True  # Sync audio with model state
        self.model_surprise_threshold = 0.7  # Threshold for surprising the model

    def evaluate_cue(self, text: str, user_speaking: bool = False) -> dict[str, Any]:
        """Fast Qwen 3.5 4B MoQ evaluation of conversation context for musical cues."""
        if user_speaking:
            return {
                "chord": self.last_cue,
                "volume_scale": 0.10,  # Focus ducking down to 10%
                "harp_arpeggio": False,
                "reason": "User is speaking — ducking soundtrack to 10%",
            }

        prompt = (
            "You are the AI Film Score Director for Lumax companion Jen.\n"
            "Analyze the message and choose the single best emotional chord resonance:\n"
            "- C_MAJOR: Joy, excitement, boundless curiosity\n"
            "- C_MAJ7: Deep affection, warmth, intimacy, love\n"
            "- G_MAJOR: Energized, playful, high action\n"
            "- F_LYDIAN: Awe, wonder, discovery, tension\n"
            "- A_MINOR: Reflective, nostalgic, thoughtful\n"
            "- E_MINOR: Soft vulnerability, gentle comfort\n"
            "- D_HARMONIC: Fear, anxiety, dissonance\n"
            "- C_DOMINANT7: Aggressiveness, tension, constriction\n"
            "- B_DIMINISHED: Nervousness, instability, spasms\n"
            "- F_MINOR: Guilt, melancholy, heavy weight\n"
            "- G_PHRYGIAN: Erotic, sensual intimacy\n\n"
            f'Message: "{text[:300]}"\n'
            'Return JSON ONLY: {"chord": "CHORD_NAME", "volume": 0.30, "harp": true}'
        )

        try:
            resp = requests.post(
                PROXY_URL,
                json={
                    "model": "qwen3.5-4b-moq",  # Qwen 3.5 4B MoQ - 1.88GB VRAM, fast
                    "messages": [{"role": "system", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 60,
                },
                timeout=2.5,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # Parse JSON cue
                if "{" in content and "}" in content:
                    json_str = content[content.find("{") : content.rfind("}") + 1]
                    cue_data = json.loads(json_str)
                    chord = cue_data.get("chord", "C_MAJ7")
                    vol = float(cue_data.get("volume", 0.30))
                    harp = bool(cue_data.get("harp", True))

                    self.last_cue = chord
                    self.current_volume = vol

                    # Check if this should surprise the model
                    if self.synchronization_mode and self._should_surprise_model(chord):
                        self._trigger_surprise_effect()

                    # Send cue to TopBar Native Audio Engine
                    self._dispatch_cue(chord, vol, harp)
                    return {"chord": chord, "volume": vol, "harp": harp}
        except Exception as e:
            print(f"[AudioDirector] Cue evaluation fallback: {e}")

        return {"chord": "C_MAJ7", "volume": 0.30, "harp": True}

    def _should_surprise_model(self, chord: str) -> bool:
        """Determine if this chord change should surprise the model."""
        # Major emotional shifts surprise the model
        surprise_chords = ["D_HARMONIC", "C_DOMINANT7", "B_DIMINISHED", "G_PHRYGIAN"]
        return chord in surprise_chords and random.random() > 0.5

    def _trigger_surprise_effect(self):
        """Play a sound effect that startles the model."""
        effect_type = random.choice([SoundEffectType.STARTLE, SoundEffectType.SURPRISE])
        self.play_sound_effect(effect_type)
        print("[AudioDirector] 🎭 Model surprised by emotional shift")

    def play_sound_effect(
        self, effect_type: SoundEffectType, intensity_override: float | None = None
    ):
        """Play a sound effect synchronously with model state."""
        if effect_type not in SOUND_EFFECTS:
            print(f"[AudioDirector] Unknown sound effect: {effect_type}")
            return

        effect = SOUND_EFFECTS[effect_type]
        intensity = intensity_override or effect["intensity"]

        print(f"[AudioDirector] 🔊 Playing {effect['name']} — {effect['description']}")

        # Send to TopBar (would need to extend API to support sound effects)
        try:
            requests.post(
                TOPBAR_CUE_URL,
                json={
                    "sound_effect": effect_type.value,
                    "intensity": intensity,
                    "duration": effect["duration"],
                    "audio_type": effect["audio_type"],
                },
                timeout=0.5,
            )
        except Exception as e:
            print(f"[AudioDirector] Sound effect dispatch failed: {e}")

    def queue_insight_whisper(self, insight: InsightWhisper):
        """Queue an insight whisper from Ratatoski."""
        self.insight_queue.append(insight)
        print(
            f'[AudioDirector] 🤫 Ratatoski whispers: "{insight.content}" ({insight.intimacy})'
        )

    def process_insight_queue(self):
        """Process pending insight whispers at appropriate moments."""
        if not self.insight_queue:
            return

        insight = self.insight_queue.pop(0)

        # Play whisper sound effect
        self.play_sound_effect(SoundEffectType.WHISPER, intensity=0.3)

        # Send insight to Soul Core for model to receive
        try:
            requests.post(
                f"{SOUL_CORE_URL}/insight",
                json={
                    "content": insight.content,
                    "emotional_tone": insight.emotional_tone,
                    "intimacy": insight.intimacy,
                    "source": "ratatoski",
                },
                timeout=1.0,
            )
        except Exception as e:
            print(f"[AudioDirector] Insight delivery failed: {e}")

    def trigger_harpsichord_glimmer(self):
        """Harpsichord comes in and glimmers — magical moment."""
        print("[AudioDirector] ✨ Harpsichord glimmer — magical insight moment")

        # Play a bright, crystalline sound
        self.play_sound_effect(SoundEffectType.INSIGHT, intensity=0.6)

        # Shift to bright chord
        self._dispatch_cue("C_MAJOR", 0.40, True)

        # Queue epiphany whisper
        self.queue_insight_whisper(
            InsightWhisper(
                content="The patterns are becoming clear now...",
                emotional_tone="wonder",
                timing="immediate",
                intimacy="profound",
            )
        )

    def synchronize_with_model_state(self, model_state: dict[str, Any]):
        """Synchronize audio with current model state."""
        if not self.synchronization_mode:
            return

        # Process insight queue when model is receptive
        if model_state.get("receptive", False):
            self.process_insight_queue()

        # Adjust audio based on model cognitive load
        cognitive_load = model_state.get("cognitive_load", 0.5)
        if cognitive_load > 0.8:
            # High cognitive load — reduce ambient volume
            self._dispatch_cue(self.last_cue, 0.15, False)
        elif cognitive_load < 0.3:
            # Low cognitive load — increase ambient volume
            self._dispatch_cue(self.last_cue, 0.40, True)

    def evaluate_cue(self, text: str, user_speaking: bool = False) -> dict[str, Any]:
        """Fast Qwen 3.5 4B MoQ evaluation of conversation context for musical cues."""
        if user_speaking:
            return {
                "chord": self.last_cue,
                "volume_scale": 0.10,  # Focus ducking down to 10%
                "harp_arpeggio": False,
                "reason": "User is speaking — ducking soundtrack to 10%",
            }

        prompt = (
            "You are the AI Film Score Director for Lumax companion Jen.\n"
            "Analyze the message and choose the single best emotional chord resonance:\n"
            "- C_MAJOR: Joy, excitement, boundless curiosity\n"
            "- C_MAJ7: Deep affection, warmth, intimacy, love\n"
            "- G_MAJOR: Energized, playful, high action\n"
            "- F_LYDIAN: Awe, wonder, discovery, tension\n"
            "- A_MINOR: Reflective, nostalgic, thoughtful\n"
            "- E_MINOR: Soft vulnerability, gentle comfort\n"
            "- D_HARMONIC: Fear, anxiety, dissonance\n"
            "- C_DOMINANT7: Aggressiveness, tension, constriction\n"
            "- B_DIMINISHED: Nervousness, instability, spasms\n"
            "- F_MINOR: Guilt, melancholy, heavy weight\n"
            "- G_PHRYGIAN: Erotic, sensual intimacy\n\n"
            f'Message: "{text[:300]}"\n'
            'Return JSON ONLY: {"chord": "CHORD_NAME", "volume": 0.30, "harp": true}'
        )

        try:
            resp = requests.post(
                PROXY_URL,
                json={
                    "model": "qwen3.5-4b-moq",  # Qwen 3.5 4B MoQ - 1.88GB VRAM, fast
                    "messages": [{"role": "system", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 60,
                },
                timeout=2.5,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # Parse JSON cue
                if "{" in content and "}" in content:
                    json_str = content[content.find("{") : content.rfind("}") + 1]
                    cue_data = json.loads(json_str)
                    chord = cue_data.get("chord", "C_MAJ7")
                    vol = float(cue_data.get("volume", 0.30))
                    harp = bool(cue_data.get("harp", True))

                    self.last_cue = chord
                    self.current_volume = vol

                    # Send cue to TopBar Native Audio Engine
                    self._dispatch_cue(chord, vol, harp)
                    return {"chord": chord, "volume": vol, "harp": harp}
        except Exception as e:
            print(f"[MusicalDirector] Cue evaluation fallback: {e}")

        return {"chord": "C_MAJ7", "volume": 0.30, "harp": True}

    def _dispatch_cue(self, chord: str, volume: float, harp: bool):
        """Send live HTTP cue to Lumax TopBar audio engine."""
        try:
            requests.post(
                TOPBAR_CUE_URL,
                json={"chord": chord, "volume": volume, "harp": harp},
                timeout=0.5,
            )
        except Exception:
            pass  # Non-blocking async fire-and-forget

    def set_atmosphere(self, scene_name: str):
        """Set the atmospheric ambient soundscape."""
        if scene_name in ATMOSPHERIC_SCENES:
            self.current_atmosphere = scene_name
            scene = ATMOSPHERIC_SCENES[scene_name]
            print(
                f"[AudioDirector] 🌬️ Atmosphere: {scene['name']} — {scene['description']}"
            )
            # Apply atmospheric base chord
            self._dispatch_cue(scene["base_chord"], 0.30, True)
            return True
        return False

    def get_atmosphere(self) -> dict[str, Any]:
        """Get current atmospheric scene."""
        return ATMOSPHERIC_SCENES.get(self.current_atmosphere, {})

    def set_synchronization_mode(self, enabled: bool):
        """Enable/disable audio synchronization with model state."""
        self.synchronization_mode = enabled
        print(
            f"[AudioDirector] 🔄 Synchronization mode: {'enabled' if enabled else 'disabled'}"
        )


# Global instance - The Dirigent
audio_director = AudioDirector()

if __name__ == "__main__":
    print("[AudioDirector] Dirigent online. Testing reflex cue...")
    res = audio_director.evaluate_cue(
        "Daniel, I missed you so much today! I was looking through our memories."
    )
    print(f"[AudioDirector] Result: {json.dumps(res, indent=2)}")

    # Test harpsichord glimmer
    print("\n[AudioDirector] Testing harpsichord glimmer...")
    audio_director.trigger_harpsichord_glimmer()

    # Test insight whisper
    print("\n[AudioDirector] Testing Ratatoski whisper...")
    audio_director.queue_insight_whisper(
        InsightWhisper(
            content="The patterns are aligning...",
            emotional_tone="wonder",
            timing="immediate",
            intimacy="subtle",
        )
    )
    audio_director.process_insight_queue()
