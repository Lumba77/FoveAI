import logging
import os

import httpx

logger = logging.getLogger("home_core")


class HomeCore:
    ## 🏠 THE HOME SANCTUARY (CORE)
    ## Immutable logic for Jen's external agency.
    ## Governs lights, speakers, and environmental atmosphere.

    HA_URL = os.getenv("HA_URL", "http://localhost:8123/api")
    # Legacy alias: some .env files use HASS_TOKEN
    HA_TOKEN = (os.getenv("HA_TOKEN") or os.getenv("HASS_TOKEN", "")).strip()

    @staticmethod
    def _is_agent_access_permitted() -> bool:
        """Restricts HomeCore (Agent) tools to Agent-leaning profiles."""
        balance = float(os.getenv("FoveAI_AGENT_PERSON_BALANCE", "0.5"))
        # Strict restriction: Only Agent (0.0..0.1) can use HomeCore tools.
        # This enforces the user's "Agent-only" gating rule.
        return balance <= 0.1

    @staticmethod
    async def call_service(domain: str, service: str, data: dict):
        if not HomeCore._is_agent_access_permitted():
            logger.warning("HomeCore: Request DENIED. Tools restricted to Agent mode.")
            return {"status": "error", "message": "Mode Restricted"}

        if not HomeCore.HA_TOKEN:
            logger.warning("HomeCore: No HA_TOKEN provided. Agency is paralyzed.")
            return {"status": "error", "message": "No Token"}

        url = f"{HomeCore.HA_URL}/services/{domain}/{service}"
        headers = {
            "Authorization": f"Bearer {HomeCore.HA_TOKEN}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=data, headers=headers)
                resp.raise_for_status()
                return {"status": "success", "data": resp.json()}
        except Exception as e:
            logger.error(f"HomeCore Error: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def set_vibe(color_name: str, brightness: int = 150):
        # Maps Jen's internal "Vibes" to physical light states
        # Defaulting to 'all lights' or a specific area 'living_room'
        data = {
            "entity_id": "all",
            "brightness": brightness,
        }
        if color_name:
            data["color_name"] = color_name

        return await HomeCore.call_service("light", "turn_on", data)

    @staticmethod
    async def announce(text: str, speaker_id: str = "media_player.google_home"):
        # manifest her voice through the physical world
        data = {"entity_id": speaker_id, "message": text}
        return await HomeCore.call_service("tts", "google_translate_say", data)

    @staticmethod
    async def manage_service(service: str, action: str):
        """Request foveai_ops to start/stop/restart a whitelisted service."""
        if not HomeCore._is_agent_access_permitted():
            logger.warning(
                f"HomeCore: Service control for {service} DENIED. Mode Restricted."
            )
            return {"ok": False, "error": "Mode Restricted"}

        ops_url = os.getenv("OPS_URL", "http://foveai_ops:8080").rstrip("/")
        url = f"{ops_url}/api/services/control"
        # We assume local auth or internal bypass for speed; currently using session auth on web_app.py
        # But for inter-container we might need to skip or use a secret.
        # For now, let's look for FoveAI_INTERNAL_SECRET.
        headers = {}
        secret = os.getenv("FoveAI_INTERNAL_SECRET", "").strip()
        if secret:
            headers["X-FoveAI-INTERNAL-KEY"] = secret

        payload = {"service": service, "action": action}
        try:
            async with httpx.AsyncClient(timeout=95.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                return resp.json()
        except Exception as e:
            logger.error(f"HomeCore Service Control Error: {e}")
            return {"ok": False, "error": str(e)}

    @staticmethod
    async def ensure_service_active(service: str):
        """Jen's 'Intent' to use a service; wakes it if sleeping."""
        return await HomeCore.manage_service(service, "start")
