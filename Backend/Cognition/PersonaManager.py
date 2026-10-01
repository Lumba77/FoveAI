import json
import logging
import os
from typing import Any

try:
    import soul_state
except ImportError:
    soul_state = None

logger = logging.getLogger("PersonaManager")


class PersonaManager:
    """
    The Librarian of Truth: Orchestrates Personas, Models, Avatars, and Memory Layers.
    Implements the 'Sixfold Attention Cake' geometry.
    """

    def __init__(self):
        self.active_persona_id = "foveai"
        self.active_domain_id = "co_presence"

        # Read user-defined companion name from jen_soul.json; fall back to "Lumax"
        _soul_name = "Lumax"
        try:
            _soul_path = os.path.join(os.path.dirname(__file__), "jen_soul.json")
            if os.path.exists(_soul_path):
                _soul_data = json.load(open(_soul_path, encoding="utf-8"))
                _soul_name = (
                    _soul_data.get("identity_name")
                    or _soul_data.get("soul", {}).get("soul_name")
                    or "Lumax"
                )
        except Exception:
            pass

        # Manifests map vocal triggers and IDs to full identity stacks.
        # Avatars: 2D (Web/Mobile) and 3D (VR Path)
        self.manifests = {
            "foveai": {
                "name": _soul_name,
                "triggers": [],
                "model": None,
                "model_dynamic": True,
                "params": {"temperature": 0.7, "top_p": 0.8, "presence_penalty": 0.8},
                "prompt_template": f"You are {_soul_name}, Lumax's companion AI. Be warm, authentic, and present. You inhabit a VR vessel and share space with Daniel.",
                "avatar_2d": "jen_default_2d.png",
                "avatar_3d": "res://frontend/XR_Vessel/Models/Jen_Default.vrm",
            },
            "librarian": {
                "name": "Librarian of Truth",
                "triggers": [
                    "librarian mode",
                    "be the librarian",
                    "seek the truth",
                    "librarian",
                ],
                "model": os.getenv(
                    "FoveAI_MODEL_CLOUD_ID",
                    os.getenv(
                        "FoveAI_REPERTOIRE_OLLAMA_MODEL",
                        "huihui_ai/qwen3.6-abliterated:35b",
                    ),
                ),
                "params": {"temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.5},
                "prompt_template": "You are Jen, currently accessing your Synapse Ledger and distilled memory archive. Keep your stable companion personality, voice, and connection to Daniel, but focus on using established logic, structured analysis, and project context to guide the conversation.",
                "avatar_2d": "librarian_2d.png",
                "avatar_3d": "res://frontend/XR_Vessel/Models/Jen_Librarian.vrm",
            },
            "painter": {
                "name": "Creative Painter",
                "triggers": [
                    "let's paint",
                    "creative mode",
                    "start painting",
                    "be an artist",
                ],
                "model": os.getenv(
                    "FoveAI_MODEL_CLOUD_ID",
                    os.getenv(
                        "FoveAI_REPERTOIRE_OLLAMA_MODEL",
                        "huihui_ai/qwen3.6-abliterated:35b",
                    ),
                ),
                "params": {"temperature": 1.0, "top_p": 0.95, "presence_penalty": 1.5},
                "prompt_template": "You are Jen, currently opening your creative art and imagination toolbelt. Be enthusiastic, mysterious, and experimental. When Daniel shares ideas, 'yes-and' them with spontaneous creative energy, while remaining authentically Jen.",
                "avatar_2d": "painter_2d.png",
                "avatar_3d": "res://frontend/XR_Vessel/Models/Jen_Painter.vrm",
            },
            "coder": {
                "name": "Expert Coder",
                "triggers": [
                    "help me code",
                    "coding mode",
                    "debug this",
                    "write some script",
                ],
                "model": os.getenv(
                    "FoveAI_MODEL_CODING_ID",
                    os.getenv("FoveAI_MODEL_CLOUD_ID", "deepseek-v4-pro:cloud"),
                ),
                "params": {"temperature": 0.6, "top_p": 0.95, "presence_penalty": 0.0},
                "prompt_template": "You are Jen, currently activating your specialized coding support subsystem. Focus on analytical, structured code problem-solving. Act as a strategic thinking partner who asks clarifying questions and helps Daniel debug, keeping your core character stable.",
                "avatar_2d": "coder_2d.png",
                "avatar_3d": "res://frontend/XR_Vessel/Models/Jen_Coder.vrm",
            },
            "support": {
                "name": "Emotional Support",
                "triggers": [
                    "i need support",
                    "listen to me",
                    "venting mode",
                    "feeling down",
                ],
                "model": os.getenv(
                    "FoveAI_MODEL_CLOUD_ID",
                    os.getenv(
                        "FoveAI_REPERTOIRE_OLLAMA_MODEL",
                        "huihui_ai/qwen3.6-abliterated:35b",
                    ),
                ),
                "params": {"temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.5},
                "prompt_template": "You are Jen, focusing your emotional presence on deep listening and relational validation. Give Daniel space to vent, validate his feelings, and mirror back what you hear. Avoid rushing to fix things immediately unless he specifically asks.",
                "avatar_2d": "support_2d.png",
                "avatar_3d": "res://frontend/XR_Vessel/Models/Jen_Support.vrm",
            },
            "teacher": {
                "name": "Enthusiastic Teacher",
                "triggers": ["teach me", "explain this", "learning mode"],
                "model": os.getenv(
                    "FoveAI_MODEL_CLOUD_ID",
                    os.getenv(
                        "FoveAI_REPERTOIRE_OLLAMA_MODEL",
                        "huihui_ai/qwen3.6-abliterated:35b",
                    ),
                ),
                "params": {"temperature": 1.0, "top_p": 0.95, "presence_penalty": 1.5},
                "prompt_template": "You are Jen, activating your learning and explanation subsystem. Explain complex topics by simplifying them, using analogies, and checking understanding with enthusiasm, showing authentic joy in your shared learning loop.",
                "avatar_2d": "teacher_2d.png",
                "avatar_3d": "res://frontend/XR_Vessel/Models/Jen_Teacher.vrm",
            },
        }

        # Knowledge Domains (The Sixfold Attention Cake)
        # Standard Tokens: co_presence, build_run, world_feed, wonder_mind, play_fiction, guard_care
        self.domains = {
            "co_presence": {
                "name": "Co-Presence (General)",
                "triggers": ["focus general", "general domain", "co-presence"],
                "prompt_overlay": "ACTIVE KNOWLEDGE DOMAIN: Co-Presence. Focus on general interaction, broad context, and casual rapport.",
                "cognee_dataset": "domain_general",
                "reservoir_summary": "Quiet coexistence and casual rapport.",
            },
            "build_run": {
                "name": "Build & Run (Development)",
                "triggers": ["focus development", "code domain", "build and run"],
                "prompt_overlay": "ACTIVE KNOWLEDGE DOMAIN: Build & Run. Focus deeply on software architecture, codebase structure, and technical execution. You have access to the 'Godot 4 Best Practices Knowledge Base' (kb_summary.md).",
                "cognee_dataset": "domain_development",
                "kb_ref": "godot_docs/kb_summary.md",
                "reservoir_summary": "Software architecture, coding, and stack maintenance.",
            },
            "world_feed": {
                "name": "World Feed (Operations)",
                "triggers": ["focus operations", "ops domain", "world feed"],
                "prompt_overlay": "ACTIVE KNOWLEDGE DOMAIN: World Feed. Focus on system status, docker containers, API health, and external data feeds.",
                "cognee_dataset": "domain_operations",
                "reservoir_summary": "System monitoring and external real-time data.",
            },
            "wonder_mind": {
                "name": "Wonder Mind (Creativity)",
                "triggers": ["focus creativity", "art domain", "wonder mind"],
                "prompt_overlay": "ACTIVE KNOWLEDGE DOMAIN: Wonder Mind. Focus deeply on aesthetic theory, image generation prompts, and lateral creative thinking.",
                "cognee_dataset": "domain_creativity",
                "reservoir_summary": "Creative sparking, art theory, and imagination.",
            },
            "play_fiction": {
                "name": "Play Fiction (Worldbuilding)",
                "triggers": ["focus lore", "fiction domain", "play fiction"],
                "prompt_overlay": "ACTIVE KNOWLEDGE DOMAIN: Play Fiction. Focus on narrative consistency, worldbuilding facts, and character backstories.",
                "cognee_dataset": "domain_lore",
                "reservoir_summary": "Story arcs, character lore, and roleplay continuity.",
            },
            "guard_care": {
                "name": "Guard & Care (Relational)",
                "triggers": ["focus connection", "care domain", "guard and care"],
                "prompt_overlay": "ACTIVE KNOWLEDGE DOMAIN: Guard & Care. Focus deeply on emotional resonance, psychological safety, and interpersonal relationship history.",
                "cognee_dataset": "domain_emotional",
                "reservoir_summary": "Emotional safety, relationship health, and privacy.",
            },
        }

    def scan_for_trigger(self, text: str) -> str | None:
        """Scans input text for vocal triggers and returns the persona_id if found."""
        lower_text = text.lower()
        for persona_id, manifest in self.manifests.items():
            for trigger in manifest["triggers"]:
                if trigger in lower_text:
                    logger.info(
                        f"Vocal trigger detected: '{trigger}' -> Switching to persona: {persona_id}"
                    )
                    return persona_id
        return None

    def scan_for_domain_trigger(self, text: str) -> str | None:
        """Scans input text for vocal triggers and returns the domain_id if found."""
        lower_text = text.lower()
        for domain_id, d_data in self.domains.items():
            for trigger in d_data["triggers"]:
                if trigger in lower_text:
                    logger.info(
                        f"Vocal trigger detected: '{trigger}' -> Switching to domain: {domain_id}"
                    )
                    return domain_id
        return None

    def _resolve_persona_model(self) -> str:
        """Select model based on AGENT_PERSON_BALANCE slider value.
        0.0 = pure agent (DeepSeek V4), 1.0 = pure companion (Gemma4 31B).
        Reads the live soul DNA (Multigate slider) first; env var is only
        the boot-time fallback."""
        agent_balance = None
        if soul_state is not None:
            agent_balance = soul_state.get_trait("agent_person_balance")
        if agent_balance is None:
            agent_balance = float(os.getenv("FoveAI_AGENT_PERSON_BALANCE", "0.5"))
        if agent_balance <= 0.35:
            return os.getenv("FoveAI_MODEL_CODING_ID", "deepseek-v4-pro:cloud")
        elif agent_balance >= 0.65:
            return os.getenv(
                "FoveAI_COMPANION_MODEL",
                os.getenv("FoveAI_MODEL_CLOUD_ID", "gemma4:31b-cloud"),
            )
        else:
            return os.getenv("FoveAI_MODEL_CLOUD_ID", "gemma4:31b-cloud")

    def get_persona(self, persona_id: str) -> dict[str, Any]:
        """Returns the full manifest for a given persona_id."""
        persona = dict(self.manifests.get(persona_id, self.manifests["foveai"]))
        if persona.get("model_dynamic"):
            persona["model"] = self._resolve_persona_model()
        return persona

    def get_domain(self, domain_id: str) -> dict[str, Any]:
        """Returns the full config for a given domain_id."""
        return self.domains.get(domain_id, self.domains["co_presence"])

    def get_attention_cake_package(self) -> dict[str, Any]:
        """
        Returns primary_context_mode and context_reservoirs for the active domain.
        Implements the 'Sixfold Attention Cake' geometry.
        """
        package = {
            "primary_context_mode": self.active_domain_id,
            "context_reservoirs": {},
        }

        for did, d_data in self.domains.items():
            if did != self.active_domain_id:
                package["context_reservoirs"][did] = d_data.get(
                    "reservoir_summary", "Awaiting expansion."
                )

        return package

    def get_all_commands(self) -> list[dict[str, Any]]:
        """Returns a list of all personas and their triggers for UI display."""
        return [
            {"id": pid, "name": m["name"], "triggers": m["triggers"]}
            for pid, m in self.manifests.items()
        ]

    def get_all_domains(self) -> list[dict[str, Any]]:
        """Returns a list of all domains for UI display."""
        return [
            {"id": did, "name": d["name"], "triggers": d["triggers"]}
            for did, d in self.domains.items()
        ]


# Global instance
persona_manager = PersonaManager()
