"""XRL-Bridge/1.0 — Security Utilities.

- Mandatory startup bridge secret validation (fail closed)
- Canonical HMAC payload verification
- CSRF token issuance and timing-attack-safe validation
- Safe local notifications via subprocess (no shell interpolation)
- Audit logging with secret redaction
"""

import hmac
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("xrl_bridge.security")

# Fail-closed secret check
BRIDGE_SECRET_ENV = "FOVEAI_BRIDGE_SECRET"
_BRIDGE_SECRET = os.environ.get(BRIDGE_SECRET_ENV)


def get_bridge_secret() -> str:
    secret = os.environ.get(BRIDGE_SECRET_ENV)
    if not secret or len(secret.strip()) < 16:
        raise RuntimeError(
            f"FATAL: {BRIDGE_SECRET_ENV} must be set with at least 16 characters. Failing closed."
        )
    return secret.strip()


def verify_hmac_signature(payload_dict: Dict[str, Any], signature: Optional[str], secret: str) -> bool:
    """Verifies HMAC SHA-256 over canonicalized JSON representation."""
    if not signature:
        return False
    # Canonical JSON string: sorted keys, no extraneous whitespace
    canonical = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def compute_hmac_signature(payload_dict: Dict[str, Any], secret: str) -> str:
    canonical = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


# CSRF Token store for local approval sessions
_CSRF_STORE: Dict[str, float] = {}


def generate_csrf_token(task_id: str) -> str:
    token = secrets.token_hex(24)
    _CSRF_STORE[task_id] = token
    return token


def verify_csrf_token(task_id: str, submitted_token: str) -> bool:
    expected = _CSRF_STORE.get(task_id)
    if not expected:
        return False
    valid = hmac.compare_digest(expected, submitted_token)
    if valid:
        _CSRF_STORE.pop(task_id, None)  # Single-use token
    return valid


def safe_notify_send(title: str, message: str, urgency: str = "normal") -> bool:
    """Invokes notify-send safely using argument arrays without shell interpolation."""
    safe_urgency = "normal" if urgency not in ("low", "normal", "critical") else urgency
    # Sanitize and truncate inputs
    safe_title = str(title)[:100].strip()
    safe_message = str(message)[:300].strip()
    try:
        subprocess.run(
            ["notify-send", "-u", safe_urgency, safe_title, safe_message],
            check=False,
            timeout=2.0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.warning("notify-send invocation failed safely: %s", e)
        return False


SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{20,})"),
    re.compile(r"(ghp_[A-Za-z0-9]{20,})"),
    re.compile(r"(hf_[A-Za-z0-9]{20,})"),
    re.compile(r"(-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----)"),
    re.compile(r"([0-9a-fA-F]{32,64})"),
]


def redact_secrets(text: str) -> str:
    redacted = str(text)
    for pat in SECRET_PATTERNS:
        redacted = pat.sub("[REDACTED_SECRET]", redacted)
    return redacted
