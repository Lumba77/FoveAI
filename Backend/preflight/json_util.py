"""
Human-edited playbook files (watchdog policy, unstable features, etc.).

Uses JSON5 when the `json5` package is installed (// comments, trailing commas).
Falls back to stdlib `json` if not (e.g. minimal dev env).
"""

from __future__ import annotations

import json
from typing import Any, TextIO

try:
    import json5  # type: ignore[import-untyped]
except ImportError:
    json5 = None


def load_playbook_file(f: TextIO) -> Any:
    if json5 is not None:
        return json5.load(f)
    return json.load(f)


def load_playbook_path(path: str, encoding: str = "utf-8") -> Any:
    with open(path, "r", encoding=encoding) as f:
        return load_playbook_file(f)
