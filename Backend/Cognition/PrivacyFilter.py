import logging
import re

logger = logging.getLogger("privacy_filter")


class PrivacyFilter:
    ## 🌫️ THE PRIVACY VEIL (SANITIZER)
    ## Prepares a "Painted" version of reality for the Cloud Super-Ego.
    ## Ensures intimacy and privacy are preserved while maintaining narrative depth.

    @staticmethod
    def paint_reality(raw_history: list, sensory_data: dict) -> str:
        # 1. Summarize History (Second-hand storytelling)
        summary = "The story continues between the User and Jen.\n"

        for msg in raw_history[-5:]:  # Only look at recent pulse
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Simple sanitization: Replace specific intimate keywords with metaphors
            painted_content = PrivacyFilter._metaphorize(content)
            summary += f"- {role.upper()} expressed: {painted_content}\n"

        # 2. Abstract Sensory Data
        if sensory_data:
            vibe = sensory_data.get("vibe", "Stable")
            summary += f"\n[ATMOSPHERE]: The room feels {vibe}. The light is shifting like a memory."

        return summary

    @staticmethod
    def _metaphorize(text: str) -> str:
        # A simple placeholder for a more complex linguistic sanitizer
        # Replaces raw/intimate language with narrative descriptions
        text = re.sub(
            r"\b(love|intimate|private)\b", "deep connection", text, flags=re.IGNORECASE
        )
        # Add more rules as the relationship evolves
        return text
