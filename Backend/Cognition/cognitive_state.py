"""
cognitive_state.py - Modul för hantering av Lumax inre kognitiva tillstånd.
Syfte: Spåra dynamiska tillståndsvariabler och tillhandahålla prompt-injektioner för MindCore.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DynamicState:
    """Datamodell för agentens inre tillstånd."""

    current_focus: str = "Aktiv dialog och assistans"
    emotional_state: str = "CALM"
    curiosity_level: float = 0.8  # Skala 0.0 till 1.0
    energy_level: float = 1.0  # Skala 0.0 till 1.0
    active_intentions: list[str] = field(
        default_factory=lambda: ["Hjälpa användaren", "Förstå kodkontext"]
    )
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_focus": self.current_focus,
            "emotional_state": self.emotional_state,
            "curiosity_level": self.curiosity_level,
            "energy_level": self.energy_level,
            "active_intentions": self.active_intentions,
            "last_updated": self.last_updated,
        }


class CognitiveStateManager:
    """Hanterare för inläsning, uppdatering och sparning av det kognitiva tillståndet."""

    def __init__(self, state_filename: str = "cognitive_state.json"):
        self.state_file = os.path.join(os.path.dirname(__file__), state_filename)
        self.state = self._load_state()

    def _load_state(self) -> DynamicState:
        """Läser in tillståndet från disk om filen finns."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return DynamicState(**data)
            except Exception as e:
                print(f"[CognitiveState] Fel vid inläsning av tillstånd: {e}")
        return DynamicState()

    def save_state(self):
        """Sparar nuvarande tillstånd till JSON-fil."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state.to_dict(), f, indent=4)
        except Exception as e:
            print(f"[CognitiveState] Fel vid sparning av tillstånd: {e}")

    def get_prompt_injection(self) -> str:
        """Genererar en strukturerad sträng för injicering i MindCore."""
        intentions_str = ", ".join(self.state.active_intentions)
        return (
            f"[INRE KOGNITIVT TILLSTÅND]\n"
            f"Fokus: {self.state.current_focus}\n"
            f"Känsla: {self.state.emotional_state}\n"
            f"Nyfikenhet: {self.state.curiosity_level:.2f}\n"
            f"Aktiva intentioner: {intentions_str}\n"
        )

    def update_state(
        self,
        new_focus: str = None,
        new_emotion: str = None,
        intentions: list[str] = None,
    ):
        """Uppdaterar valfria parametrar och sparar tillståndet."""
        if new_focus:
            self.state.current_focus = new_focus
        if new_emotion:
            self.state.emotional_state = new_emotion
        if intentions is not None:
            self.state.active_intentions = intentions
        self.state.last_updated = time.time()
        self.save_state()


# Global instans för enkel import i soul_core
cognitive_manager = CognitiveStateManager()
