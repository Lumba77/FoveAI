import logging
from typing import Any

logger = logging.getLogger("RatatoskVeil")


class RatatoskVeil:
    """
    The Ratatosk Veil acts as the intermediator between the local Alicechan context
    (soul_core) and the cloud-based Director Manager.

    Like the mythological squirrel Ratatosk running up and down the World Tree,
    it abstracts and sanitizes the local context to protect the user's intimate
    details before passing it up to the 'God Perspective' in the cloud.
    """

    def __init__(self):
        self.privacy_rules = [
            # Basic redaction rules for PII and intimate details
            {
                "pattern": r"\b(password|secret|token)\b",
                "replacement": "[REDACTED_AUTH]",
            },
            {
                "pattern": r"\b(credit card|ssn)\b",
                "replacement": "[REDACTED_FINANCIAL]",
            },
            # In a real system, this would use a localized NLP NER model to strip names/locations
        ]
        logger.info("Ratatosk Veil initialized. Privacy abstraction active.")

    def abstract_context(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        """
        Takes the raw sensory and conversational context from the XR vessel
        and strips away intimate nitty-gritty details, leaving only the
        high-level storyline and archetypal interactions.
        """
        abstracted = {}

        # 1. Sanitize Chat History
        if "chat_history" in raw_context:
            abstracted["narrative_arc"] = self._sanitize_text_batch(
                raw_context["chat_history"]
            )

        # 2. Abstract Spatial Data
        if "spatial_data" in raw_context:
            abstracted["environment"] = self._abstract_spatial(
                raw_context["spatial_data"]
            )

        # 3. Emotional State
        if "emotional_state" in raw_context:
            abstracted["avatar_emotion"] = raw_context["emotional_state"]

        # 4. User Interaction Level
        abstracted["user_engagement"] = raw_context.get("engagement_level", "neutral")

        return abstracted

    def _sanitize_text_batch(self, chat_lines: list[str]) -> list[str]:
        sanitized = []
        for line in chat_lines:
            s_line = line
            # Naive regex replacement for demonstration.
            # Production would use presidio-analyzer or local LLM abstraction.
            import re

            for rule in self.privacy_rules:
                s_line = re.sub(
                    rule["pattern"], rule["replacement"], s_line, flags=re.IGNORECASE
                )

            # Further abstract the exact words into narrative beats
            if "User:" in s_line:
                s_line = "User provided input/question."
            elif "Alice:" in s_line:
                s_line = "Alice responded to input."

            sanitized.append(s_line)
        return sanitized

    def _abstract_spatial(self, spatial_data: dict[str, Any]) -> str:
        """Converts raw room geometry into a high-level scene description."""
        num_objects = len(spatial_data.get("bounding_boxes", []))
        return f"An indoor space with {num_objects} primary obstacles/furniture pieces."

    async def carry_to_director(
        self, raw_context: dict[str, Any], director_manager: Any
    ):
        """
        Ratatosk runs up the tree.
        Abstracts the context and passes it to the Director.
        """
        safe_context = self.abstract_context(raw_context)
        logger.info("Ratatosk has sanitized the context. Passing to Director.")

        # Await the Director's asynchronous plotting
        thought_impulse = await director_manager.process_narrative_arc(safe_context)
        return thought_impulse
