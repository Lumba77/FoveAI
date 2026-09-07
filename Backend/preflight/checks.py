import os
import logging
from dataclasses import dataclass, asdict
from typing import List

import httpx


logger = logging.getLogger("Preflight")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    critical: bool = False
    healed: bool = False


def _service_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url)
            return r.status_code == 200
    except Exception:
        return False


def _resolved_tts_backend() -> str:
    """
    Active mouth stack: turbo or chatterbox.
    Source order: marker file first, then env, then turbo.
    """
    marker = os.getenv("FoveAI_TTS_BACKEND_FILE", "/app/Backend/preflight/tts_backend").strip()
    if marker:
        try:
            if os.path.isfile(marker):
                with open(marker, "r", encoding="utf-8-sig") as f:
                    first = (f.readline() or "").strip().lower()
                    if first in ("turbo", "chatterbox"):
                        return first
        except Exception:
            pass
    env_v = os.getenv("FoveAI_TTS_BACKEND", "turbo").strip().lower()
    return env_v if env_v in ("turbo", "chatterbox") else "turbo"


def run_preflight(level: str = "light", autoheal: bool = True) -> List[CheckResult]:
    """
    Lightweight backend-side preflight for sentry loops.
    Levels:
      - light: critical local checks only
      - standard: + container service checks
      - deep: + soul bridge localhost probe
    """
    level = (level or "light").strip().lower()
    if level not in {"light", "standard", "deep"}:
        level = "light"

    results: List[CheckResult] = []

    # Critical baseline checks
    app_root = os.getenv("FoveAI_APP_ROOT", "/app")
    godot_dir = os.path.join(app_root, "Godot")
    results.append(
        CheckResult(
            name="project_root",
            ok=os.path.isdir(app_root),
            detail=f"root={app_root}",
            critical=True,
        )
    )
    results.append(
        CheckResult(
            name="godot_dir",
            ok=os.path.isdir(godot_dir),
            detail=f"godot={godot_dir}",
            critical=True,
        )
    )

    if level in {"standard", "deep"}:
        # Services inside compose network
        tts_backend = _resolved_tts_backend()
        services = {
            "soul_health": "http://foveai_soul:8402/health",
            "ears_health": "http://foveai_body:8001/health",
            "mouth_health": "http://foveai_body:8002/health",
        }
        if tts_backend == "turbo":
            services["turbo_health"] = "http://foveai_turbochat:8005/health"
        for name, url in services.items():
            ok = _service_ok(url)
            results.append(
                CheckResult(
                    name=name,
                    ok=ok,
                    detail=url,
                    critical=(name == "soul_health"),
                )
            )

    if level == "deep":
        # On device/host side this would be 127.0.0.1:8000; inside container this may be false by design.
        # Keep non-critical to avoid false red in compose networking.
        bridge_url = os.getenv("FoveAI_PREFLIGHT_BRIDGE_URL", "http://127.0.0.1:8402/health")
        bridge_ok = _service_ok(bridge_url, timeout=2.0)
        results.append(
            CheckResult(
                name="bridge_loopback_probe",
                ok=bridge_ok,
                detail=bridge_url,
                critical=False,
            )
        )

    # Simple heal hook placeholder: currently network-only checks, so heal happens in sentry bridge code.
    if autoheal:
        # Reserved for future expansion (docker restart hooks, targeted restarts, etc.)
        pass

    fails = [r for r in results if r.critical and not r.ok]
    logger.debug(
        "Preflight[%s]: critical_failures=%d total=%d",
        level,
        len(fails),
        len(results),
    )
    return results


def summarize(results: List[CheckResult]) -> str:
    return ", ".join([f"{r.name}={'OK' if r.ok else 'FAIL'}" for r in results])


def to_dict(results: List[CheckResult]):
    return [asdict(r) for r in results]

