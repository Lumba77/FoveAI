import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv, set_key
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("foveai.config_manager")

# Path to the actual .env file
ENV_FILE_PATH = (
    Path(os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent.parent))
    / ".env"
)


class ConfigManager:
    """
    The central source of truth for FoveAI configurations.
    Operates directly on the .env file so changes are persistent and instantly reflected.
    """

    def __init__(self):
        # Reload the .env file into os.environ on startup just to be sure
        if ENV_FILE_PATH.exists():
            load_dotenv(dotenv_path=ENV_FILE_PATH, override=True)
            logger.info(f"ConfigManager: Bound directly to {ENV_FILE_PATH}")
        else:
            logger.warning(f"ConfigManager: .env file not found at {ENV_FILE_PATH}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value directly from the environment."""
        return os.getenv(key, default)

    def set(self, key: str, value: Any):
        """Set a configuration value directly in the .env file and update the current process environment."""
        val_str = str(value)
        # Update the OS environment immediately so the running app sees the change
        os.environ[key] = val_str

        # Persist to the .env file
        if ENV_FILE_PATH.exists():
            try:
                set_key(str(ENV_FILE_PATH), key, val_str)
                logger.info(f"ConfigManager: Updated {key} in .env")
            except Exception as e:
                logger.error(f"ConfigManager: Failed to write {key} to .env - {e}")
        else:
            logger.error(
                f"ConfigManager: Cannot write {key}, .env file missing at {ENV_FILE_PATH}"
            )


# Singleton instance
config = ConfigManager()

# --- FastAPI Router Integration ---
config_router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, Any]


@config_router.get("/")
async def get_config():
    """Return the current dynamic environment state for the UI."""
    return {
        "status": "ok",
        "overrides": {
            # We explicitly send back the values the UI cares about
            "FoveAI_CHAT_PROVIDER": os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud"),
            "FoveAI_COGNITIVE_MODE": os.getenv("FoveAI_COGNITIVE_MODE", "normal"),
            "FoveAI_SOFT_PROMPT_TOKENS_HIGH": os.getenv(
                "FoveAI_SOFT_PROMPT_TOKENS_HIGH", "12000"
            ),
        },
    }


@config_router.post("/")
async def update_config(req: ConfigUpdateRequest):
    """Apply multiple configuration updates directly to the .env file."""
    for key, val in req.updates.items():
        config.set(key, val)
    return {"status": "ok", "message": "Written directly to .env"}
