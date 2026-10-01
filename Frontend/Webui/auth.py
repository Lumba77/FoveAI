import hashlib
import os
import secrets
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

# Production / Docker: set LUMAX_WEBUI_PASSWORD (see docker-compose lumax_ops).
# Local dev without a password: LUMAX_WEBUI_ALLOW_INSECURE=1 (never on public networks).
WEBUI_PASSWORD = os.getenv("LUMAX_WEBUI_PASSWORD", "").strip()
WEBUI_SESSION_SECRET = os.getenv("LUMAX_WEBUI_SESSION_SECRET", "").strip()
WEBUI_ALLOW_INSECURE = os.getenv("LUMAX_WEBUI_ALLOW_INSECURE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
SESSION_KEY_OK = "lumax_webui_ok"


class LoginBody(BaseModel):
    password: str = Field("", max_length=4096)


def validate_webui_auth_config() -> None:
    """Require a non-empty password unless LUMAX_WEBUI_ALLOW_INSECURE=1 (dev-only)."""
    if WEBUI_PASSWORD:
        return
    if WEBUI_ALLOW_INSECURE:
        return
    raise RuntimeError(
        "LUMAX_WEBUI_PASSWORD is empty. Set it in the environment (e.g. .env next to docker-compose), "
        "or set LUMAX_WEBUI_ALLOW_INSECURE=1 for local development only (no password gate)."
    )


def webui_session_secret() -> str:
    if WEBUI_SESSION_SECRET:
        return WEBUI_SESSION_SECRET
    if WEBUI_PASSWORD:
        return hashlib.sha256(("lumax-webui|" + WEBUI_PASSWORD).encode()).hexdigest()
    return "lumax-webui-dev-insecure-fixed-do-not-use-in-production"


def require_webui_login(request: Request) -> None:
    """Require a prior successful POST /api/auth/login when a password is configured."""
    if not WEBUI_PASSWORD:
        return
    if request.session.get(SESSION_KEY_OK):
        return
    raise HTTPException(status_code=401, detail="Not authenticated")


def password_matches(given: str) -> bool:
    try:
        return secrets.compare_digest(WEBUI_PASSWORD, given)
    except (TypeError, ValueError):
        return False


def auth_status(request: Request) -> dict[str, Any]:
    if not WEBUI_PASSWORD:
        return {"auth_required": False, "authenticated": True, "insecure": True}
    return {
        "auth_required": True,
        "authenticated": bool(request.session.get(SESSION_KEY_OK)),
        "insecure": False,
    }


def auth_login(request: Request, body: LoginBody) -> dict[str, bool]:
    if not WEBUI_PASSWORD:
        request.session[SESSION_KEY_OK] = True
        return {"ok": True}
    if not password_matches(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    request.session[SESSION_KEY_OK] = True
    return {"ok": True}
