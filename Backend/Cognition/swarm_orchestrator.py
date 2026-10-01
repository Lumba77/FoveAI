"""Swarm Orchestrator — Tiered Multi-Agent Problem Solver with Director Manager.

Coordinates a swarm of drones (Scout, Optimizer, Security Sentry) under the
supervision of the Director Manager. Features Pac-Man style 2D animation
for tracking drone positions and status in real-time.

Director Manager Integration:
- Uses cloud-based Director (deepseek-v4-pro:1m) for high-level planning
- Drones execute locally with smaller models
- Director synthesizes final verdict from drone reports
"""

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("SwarmOrchestrator")

# ── Director Manager Integration ──────────────────────────────────────────────
try:
    from director_manager import (
        DIRECTOR_AUTO_APPLY,
        DIRECTOR_CLOUD_ENABLED,
        DirectorManager,
        IndexWorker,
        run_director_analysis,
    )

    DIRECTOR_MANAGER_AVAILABLE = True
except Exception as _dm_err:
    DIRECTOR_MANAGER_AVAILABLE = False
    DirectorManager = None
    IndexWorker = None
    run_director_analysis = None
    DIRECTOR_CLOUD_ENABLED = False
    DIRECTOR_AUTO_APPLY = False
    logger.warning(f"Director Manager not available for swarm: {_dm_err}")

# ── Map/Position System for Pac-Man Style Visualizer ─────────────────────────
# Grid-based positions for drone animation (0-100 coordinates)
MAP_LOCATIONS = {
    "base": {"x": 50, "y": 50},
    "repo_root": {"x": 20, "y": 30},
    "target_files": {"x": 80, "y": 30},
    "cloud": {"x": 50, "y": 10},  # Director's cloud perch
    "analysis_zone": {"x": 70, "y": 60},
    "security_perimeter": {"x": 30, "y": 70},
    "optimization_lab": {"x": 80, "y": 70},
}


def _interpolate_position(
    from_loc: str, to_loc: str, progress: float
) -> dict[str, int]:
    """Calculate intermediate position for smooth drone animation."""
    from_pos = MAP_LOCATIONS.get(from_loc, {"x": 50, "y": 50})
    to_pos = MAP_LOCATIONS.get(to_loc, {"x": 50, "y": 50})
    return {
        "x": int(from_pos["x"] + (to_pos["x"] - from_pos["x"]) * progress),
        "y": int(from_pos["y"] + (to_pos["y"] - from_pos["y"]) * progress),
    }


# ── Global State for Visualizer ───────────────────────────────────────────────

SWARM_STATE = {
    "active": False,
    "objective": "",
    "context": "",
    "target_files": [],
    "progress_pct": 0,
    "phase": "idle",  # idle, planning, dispatching, executing, synthesizing, complete
    "director_cloud_enabled": DIRECTOR_CLOUD_ENABLED,
    "drones": {
        "director": {
            "role": "Director",
            "status": "idle",
            "location": "base",
            "message": "",
            "position": MAP_LOCATIONS["base"].copy(),
            "color": "#9b59b6",  # Purple for Director
        },
        "scout": {
            "role": "Scout",
            "status": "idle",
            "location": "base",
            "message": "",
            "position": MAP_LOCATIONS["base"].copy(),
            "color": "#3498db",  # Blue for Scout
        },
        "optimizer": {
            "role": "Optimizer",
            "status": "idle",
            "location": "base",
            "message": "",
            "position": MAP_LOCATIONS["base"].copy(),
            "color": "#2ecc71",  # Green for Optimizer
        },
        "sentry": {
            "role": "Security Sentry",
            "status": "idle",
            "location": "base",
            "message": "",
            "position": MAP_LOCATIONS["base"].copy(),
            "color": "#e74c3c",  # Red for Sentry
        },
    },
    "results": {},
}


def get_swarm_state() -> dict[str, Any]:
    """Return current swarm state for web visualizer."""
    return SWARM_STATE


def _update_drone(
    drone_id: str, status: str, location: str, message: str, progress_delta: int = 0
):
    """Update drone state with automatic position interpolation."""
    if drone_id not in SWARM_STATE["drones"]:
        return

    drone = SWARM_STATE["drones"][drone_id]
    old_location = drone["location"]

    # Interpolate position for smooth animation
    if old_location != location:
        drone["position"] = _interpolate_position(old_location, location, 0.7)

    drone["status"] = status
    drone["location"] = location
    drone["message"] = message

    # Update progress
    if progress_delta:
        SWARM_STATE["progress_pct"] = min(
            100, SWARM_STATE["progress_pct"] + progress_delta
        )

    logger.info(f"[Swarm:{drone_id.upper()}] @ {location} -> {message}")


async def _animate_drone_movement(
    drone_id: str, from_loc: str, to_loc: str, duration_sec: float = 1.0
):
    """Animate drone movement between locations for visualizer."""
    if drone_id not in SWARM_STATE["drones"]:
        return

    steps = 10
    for i in range(steps + 1):
        progress = i / steps
        pos = _interpolate_position(from_loc, to_loc, progress)
        SWARM_STATE["drones"][drone_id]["position"] = pos
        await asyncio.sleep(duration_sec / steps)


async def _drone_task(
    drone_id: str,
    role_prompt: str,
    objective: str,
    context: str,
    model: str,
    host: str,
    max_tokens: int = 256,
) -> str:
    """Execute a single drone's analysis task."""

    if drone_id != "director":
        # Animate movement to target
        await _animate_drone_movement(drone_id, "base", "repo_root", 0.5)
        _update_drone(drone_id, "investigating", "repo_root", "Reading context...")
        await asyncio.sleep(0.5)

        # Move to specific zone based on role
        zone_map = {
            "scout": "target_files",
            "optimizer": "optimization_lab",
            "sentry": "security_perimeter",
        }
        target_zone = zone_map.get(drone_id, "analysis_zone")
        await _animate_drone_movement(drone_id, "repo_root", target_zone, 0.5)
        _update_drone(drone_id, "analyzing", target_zone, "Generating insights...")

    # Build prompt
    prompt = f"{role_prompt}\n\nObjective: {objective}\n\nContext/Logs:\n{context}\n\nProvide your analysis."

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{host}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "stream": False,
                },
            )
            if resp.status_code == 200:
                answer = (
                    resp.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if drone_id != "director":
                    _update_drone(drone_id, "returning", "base", "Analysis complete.")
                    await _animate_drone_movement(
                        drone_id,
                        SWARM_STATE["drones"][drone_id]["location"],
                        "base",
                        0.5,
                    )
                return answer
            else:
                _update_drone(drone_id, "error", "base", f"HTTP {resp.status_code}")
                return f"Error: HTTP {resp.status_code}"
    except Exception as e:
        _update_drone(drone_id, "error", "base", str(e))
        return f"Exception: {e}"


async def _director_cloud_planning(
    objective: str, context: str, cloud_model: str, cloud_host: str
) -> str:
    """Director creates high-level plan using cloud model."""

    _update_drone(
        "director", "planning", "cloud", "Formulating battle plan from cloud perch..."
    )
    SWARM_STATE["phase"] = "planning"
    SWARM_STATE["progress_pct"] = 10

    # Move Director to cloud position
    SWARM_STATE["drones"]["director"]["position"] = MAP_LOCATIONS["cloud"].copy()

    director_plan_prompt = (
        "You are the Swarm Director overseeing a team of specialist drones.\n"
        "Analyze the objective and context carefully.\n"
        "Create a concise 3-point plan specifying:\n"
        "1. What the Scout should investigate\n"
        "2. What the Optimizer should improve\n"
        "3. What the Security Sentry should audit\n\n"
        "Be specific and actionable."
    )

    plan = await _drone_task(
        "director",
        director_plan_prompt,
        objective,
        context,
        cloud_model,
        cloud_host,
        max_tokens=512,
    )

    _update_drone("director", "directing", "cloud", f"Plan established: {plan[:50]}...")
    SWARM_STATE["progress_pct"] = 25
    return plan


async def _director_cloud_synthesis(
    objective: str,
    context: str,
    scout_report: str,
    optimizer_report: str,
    sentry_report: str,
    cloud_model: str,
    cloud_host: str,
) -> str:
    """Director synthesizes final verdict from drone reports."""

    _update_drone(
        "director",
        "synthesizing",
        "cloud",
        "Synthesizing drone reports into final verdict...",
    )
    SWARM_STATE["phase"] = "synthesizing"
    SWARM_STATE["progress_pct"] = 85

    synthesis_context = f"""
Original Context:
{context}

=== DRONE REPORTS ===

Scout Report:
{scout_report}

Optimizer Report:
{optimizer_report}

Sentry Report:
{sentry_report}

=== END REPORTS ===
"""

    director_synth_prompt = (
        "You are the Swarm Director. Your team has completed their analysis.\n"
        "Synthesize their findings into a final, authoritative decision.\n"
        "Provide:\n"
        "1. Root cause or key finding (from Scout)\n"
        "2. Recommended solution (from Optimizer)\n"
        "3. Risk assessment (from Sentry)\n"
        "4. Final verdict with exact code or steps needed\n\n"
        "Be decisive and provide actionable output."
    )

    final_verdict = await _drone_task(
        "director",
        director_synth_prompt,
        objective,
        synthesis_context,
        cloud_model,
        cloud_host,
        max_tokens=2048,
    )

    _update_drone(
        "director", "idle", "base", "Mission complete. Final verdict delivered."
    )
    SWARM_STATE["progress_pct"] = 100
    SWARM_STATE["phase"] = "complete"

    # Return Director to base
    SWARM_STATE["drones"]["director"]["position"] = MAP_LOCATIONS["base"].copy()

    return final_verdict


async def execute_swarm_task(objective: str, context: str) -> dict[str, Any]:
    """
    Tiered Swarm Operation with Director Manager oversight:

    PHASE 1: Director (Cloud) creates high-level plan
    PHASE 2: Drones (Local) execute specialized tasks in parallel
    PHASE 3: Director (Cloud) synthesizes final verdict

    The Pac-Man style visualizer tracks all drones in real-time.
    """

    # Reset state
    SWARM_STATE["active"] = True
    SWARM_STATE["objective"] = objective
    SWARM_STATE["context"] = context
    SWARM_STATE["progress_pct"] = 0
    SWARM_STATE["phase"] = "planning"
    SWARM_STATE["results"] = {}

    # Extract target files for visualizer
    target_files = []
    for line in context.splitlines():
        if ".py" in line or ".json" in line or ".md" in line:
            parts = line.split()
            for p in parts:
                if (
                    ("." in p and ("/" in p or "\\" in p))
                    or p.startswith("frontend/")
                    or p.startswith("backend/")
                ):
                    target_files.append(p)
    SWARM_STATE["target_files"] = list(set(target_files))[:8]

    # Configure models
    local_model = os.getenv("FoveAI_SENTRY_SOLVER_MODEL", "qwen2.5-coder:3b").strip()
    local_host = (
        os.getenv(
            "FoveAI_LOCAL_BASE_URL",
            os.getenv(
                "FoveAI_FALLBACK_BASE_URL",
                os.getenv("FoveAI_BACKUP_BASE_URL", "http://localhost:8888/v1"),
            ),
        )
        .strip()
        .rstrip("/")
    )

    # Cloud config - prefer Director Manager model if available
    if DIRECTOR_MANAGER_AVAILABLE and DIRECTOR_CLOUD_ENABLED:
        cloud_model = os.getenv(
            "FoveAI_MODEL_DIRECTOR_ID", "deepseek-v4-pro:1m"
        ).strip()
        cloud_host = (
            os.getenv("FOVEAI_DIRECTOR_BASE_URL", "https://ollama.com/v1")
            .strip()
            .rstrip("/")
        )
    else:
        cloud_model = os.getenv(
            "FoveAI_CLOUD_MODEL_CODER",
            os.getenv("FoveAI_REPERTOIRE_MODEL_CODER", "qwen3.5:397b"),
        ).strip()
        cloud_host = os.getenv("FoveAI_CLOUD_BASE_URL", local_host).strip().rstrip("/")

    logger.info(f"🚀 Launching Swarm. Director: {cloud_model}, Drones: {local_model}")
    logger.info(f"🎯 Objective: {objective[:100]}...")

    try:
        # PHASE 1: Director Planning (Cloud)
        director_plan = await _director_cloud_planning(
            objective, context, cloud_model, cloud_host
        )

        # PHASE 2: Drones Execution (Local)
        SWARM_STATE["phase"] = "executing"
        _update_drone("director", "observing", "cloud", "Monitoring drone execution...")

        roles = {
            "scout": (
                f"You are the Swarm Scout. The Director's Plan:\n{director_plan}\n\n"
                "Your mission: Read the context/logs and identify the EXACT source of the problem "
                "or the specific files/code that need implementation. Be precise with file paths and line references."
            ),
            "optimizer": (
                f"You are the Swarm Optimizer. The Director's Plan:\n{director_plan}\n\n"
                "Your mission: Analyze the code/context and suggest the most efficient, clean implementation. "
                "Provide actual code snippets or refactoring recommendations."
            ),
            "sentry": (
                f"You are the Swarm Security Sentry. The Director's Plan:\n{director_plan}\n\n"
                "Your mission: Review for edge cases, race conditions, security vulnerabilities, "
                "and potential failure modes. Flag any risks."
            ),
        }

        # Launch drones in parallel
        tasks = [
            _drone_task(
                "scout",
                roles["scout"],
                objective,
                context,
                local_model,
                local_host,
                max_tokens=512,
            ),
            _drone_task(
                "optimizer",
                roles["optimizer"],
                objective,
                context,
                local_model,
                local_host,
                max_tokens=768,
            ),
            _drone_task(
                "sentry",
                roles["sentry"],
                objective,
                context,
                local_model,
                local_host,
                max_tokens=512,
            ),
        ]

        SWARM_STATE["progress_pct"] = 50
        drone_results = await asyncio.gather(*tasks)
        SWARM_STATE["progress_pct"] = 75

        # PHASE 3: Director Synthesis (Cloud)
        final_verdict = await _director_cloud_synthesis(
            objective,
            context,
            drone_results[0],  # Scout
            drone_results[1],  # Optimizer
            drone_results[2],  # Sentry
            cloud_model,
            cloud_host,
        )

        # Build final report
        final_report = {
            "director_plan": director_plan,
            "scout": drone_results[0],
            "optimizer": drone_results[1],
            "sentry": drone_results[2],
            "final_verdict": final_verdict,
            "director_model": cloud_model,
            "drone_model": local_model,
        }

        SWARM_STATE["results"] = final_report
        SWARM_STATE["active"] = False

        logger.info(f"✅ Swarm mission complete: {objective[:50]}...")
        return final_report

    except Exception as e:
        logger.exception(f"❌ Swarm mission failed: {e}")
        SWARM_STATE["active"] = False
        SWARM_STATE["phase"] = "error"
        _update_drone("director", "error", "base", f"Mission failed: {e}")
        return {
            "error": str(e),
            "director_plan": "",
            "scout": "",
            "optimizer": "",
            "sentry": "",
            "final_verdict": "",
        }

    finally:
        # Reset all drones to idle after delay
        await asyncio.sleep(3.0)
        for drone_id in SWARM_STATE["drones"]:
            SWARM_STATE["drones"][drone_id]["status"] = "idle"
            SWARM_STATE["drones"][drone_id]["location"] = "base"
            SWARM_STATE["drones"][drone_id]["message"] = "Awaiting orders"
            SWARM_STATE["drones"][drone_id]["position"] = MAP_LOCATIONS["base"].copy()
