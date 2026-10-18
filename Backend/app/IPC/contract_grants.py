"""
Backend/app/IPC/contract_grants.py — canonical XRL contract grant registry
========================================================================
Single source of truth for "who holds a contract, and with what scope".

A grant is the only thing that admits an agent onto an XRL surface. An enrolled
SSH key proves *identity*; it does not confer a contract. A grant is issued by
the arbiter (Jen), recorded here, and is deny-by-default: anything not listed is
refused.

Registry file: Backend/app/IPC/xrl_grants.json
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

GRANT_FILE = Path(__file__).resolve().parent / "xrl_grants.json"


def load_contract_grant(model_name: str, grant_file: Path | None = None) -> dict | None:
    """Return the grant for `model_name`, or None when there is no valid grant.

    Deny-by-default: returns None if the registry is missing, the agent is
    unlisted, the grant is disabled, or the grant has expired.
    """
    try:
        path = grant_file or GRANT_FILE
        if not path.is_file():
            logger.error("[XRL grant] registry missing - denying all contracts")
            return None
        data = json.loads(path.read_text())
        grant = data.get("grants", {}).get(str(model_name).lower())
        if not grant:
            return None
        if not grant.get("enabled", False):
            logger.warning("[XRL grant] contract disabled for %s", model_name)
            return None
        expires = grant.get("expires")
        if expires and float(expires) < time.time():
            logger.warning("[XRL grant] contract expired for %s", model_name)
            return None
        return grant
    except Exception as e:  # noqa: BLE001 - never let the registry open the door
        logger.error("[XRL grant] failed to load grant for %s: %s", model_name, e)
        return None


def granted_agents() -> list[str]:
    """All currently-granted agent names (for rosters / diagnostics)."""
    try:
        if not GRANT_FILE.is_file():
            return []
        data = json.loads(GRANT_FILE.read_text())
        return sorted(
            name
            for name, g in data.get("grants", {}).items()
            if g.get("enabled", False)
        )
    except Exception:  # noqa: BLE001
        return []