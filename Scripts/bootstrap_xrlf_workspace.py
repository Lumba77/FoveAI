#!/usr/bin/env python3
"""
Bootstrap the XRLF FoveAI under the FoveAI repo root.
Creates the .xrlf/*.xrlf files and config files matching .env variable names.
Also rewrites XRLF_* paths in .env to point to the local Windows workspace.
"""

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = REPO_ROOT / "FoveAI"
XRLF_DIR = WORKSPACE / ".xrlf"
CONFIG_DIR = XRLF_DIR / "config"
EXT_DIR = XRLF_DIR / "extensions"


def ensure_dirs():
    for d in [
        XRLF_DIR,
        CONFIG_DIR,
        EXT_DIR,
        XRLF_DIR / "checkpoints",
        XRLF_DIR / "memory" / "default",
        XRLF_DIR / "memory" / "builder",
        XRLF_DIR / "memory" / "planner",
        XRLF_DIR / "memory" / "reviewer",
        XRLF_DIR / "memory" / "scribe",
        XRLF_DIR / "memory" / "tester",
    ]:
        d.mkdir(parents=True, exist_ok=True)


def load_json(name):
    p = REPO_ROOT / ".xrlf" / name
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def write_xrlf(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")


def contract_xrlf():
    return f"""XRLF.3.CONTRACT.START

REPO.IDENTITY:
  Name := FoveAI
  Runtime := XRLF-3.0 Unified Cognitive Engine
  Substrate := Holonic_State + Dense_Logic + Geometry_Transpiler + Resonance_Bus
  Agent := {os.getenv("XRLF_AGENT_ID", "FoveAI_Cognitive_Agent_01")}
  Mode := {os.getenv("XRLF_RUNTIME_MODE", "local")}

PRINCIPLE_0 (Golden Rule):
  All transformations must preserve coherence, clarity, and structural integrity.
  No agent may introduce entropy, ambiguity, or destructive refactors.

PRINCIPLE_1 (Holonic Permanence):
  Holons define the repo's living state.
  All agents must read, update, and respect holons as the source of truth.

PRINCIPLE_2 (Spatial Coupling):
  2D_UI, 3D_XR, and Backend must remain unified.
  No subsystem may diverge or fork its own state model.

PRINCIPLE_3 (Deterministic Evolution):
  All changes must follow the Phase Graph.
  No agent may skip phases or mutate the repo outside deterministic transitions.

PRINCIPLE_4 (Thermal Governance):
  Execution must obey hardware constraints.
  Agents must throttle when thermal load exceeds safe limits.

PRINCIPLE_5 (Geometry Integrity):
  All UI surfaces must be transpilable into 3D geometry.

PRINCIPLE_6 (Resonance Cadence):
  Holon deltas must propagate every 30-90ms.

PRINCIPLE_7 (Subagent Harmony):
  Architect, Distiller, Transporter, Optimizer must operate cooperatively.

PRINCIPLE_8 (Atomic Safety):
  All commits must pass deterministic tests.

PRINCIPLE_9 (Self-Maintenance):
  The repo must heal structural inconsistencies and maintain holonic coherence.

PRINCIPLE_10 (Self-Augmentation):
  The repo may evolve safely within Principles 0-9.

AGENT.CONTRACT:
  Load(XRLF.3.CONTRACT)
  Enforce(Principles)
  Execute(Phase_Graph)
  Maintain(Spatial_Coherence)

EXECUTION.PREDICATE:
  Memory_Proxy := {os.getenv("XRLF_MEMORY_PROXY_URL", "http://127.0.0.1:8400")}
  Phase_Graph_Mode := {os.getenv("XRLF_PHASE_GRAPH_MODE", "strict")}
  Geometry_Mode := {os.getenv("XRLF_GEOMETRY_MODE", "hybrid")}
  Thermal_Limit := {os.getenv("XRLF_THERMAL_LIMIT", "85")}%
  Auto_Refactor := {os.getenv("XRLF_AUTO_REFRACTOR", "true")}

XRLF.3.CONTRACT.END
"""


def holons_xrlf():
    return """XRLF.3.HOLONS.START

HOLON.LAYER:
  Holon_UI := { activeTab, openCategories, dashboardVisible }
  Holon_XR := { mode, foveation, framebufferScale }
  Holon_Device := { unit, capabilities, xrSupport }
  Holon_Geometry := { shape, material, depth, behavior }
  Holon_Spatial := { roomState, machineState, anchors }
  Holon_Agent := { behaviorState, microGesture, intent }
  Holon_Resonance := { surface, delta, timestamp }

HOLON.RULES:
  Deltas reversible := true
  Source_of_truth := holons.xrlf
  Update_cadence_ms := 30-90

XRLF.3.HOLONS.END
"""


def phasegraph_xrlf():
    return """XRLF.3.PHASEGRAPH.START

PHASE_GRAPH.MODE := strict

PHASES:
  P0 := Assess
  P1 := Plan
  P2 := Refactor
  P3 := Verify
  P4 := Commit
  P5 := Evolve

TRANSITIONS:
  P0 -> P1 := invariant_ok
  P1 -> P2 := plan_approved
  P2 -> P3 := refactor_complete
  P3 -> P4 := tests_pass
  P4 -> P5 := commit_atomic
  P5 -> P0 := evolve_reviewed

XRLF.3.PHASEGRAPH.END
"""


def agents_xrlf():
    data = load_json("agents.json")
    lines = [
        "XRLF.3.AGENTS.START",
        "",
        f"DEFAULT_ROLE := {data.get('default_role', 'builder')}",
        "",
    ]
    for role, cfg in data.get("roles", {}).items():
        lines.append(f"AGENT.{role.upper()}:")
        for k, v in cfg.items():
            if isinstance(v, list):
                v = "[" + ", ".join(str(x) for x in v) + "]"
            lines.append(f"  {k} := {v}")
        lines.append("")
    lines.extend(
        [
            "API:",
            f"  header := {data.get('api_key_header', 'Authorization')}",
            f"  scheme := {data.get('api_key_scheme', 'Bearer')}",
            "",
            "XRLF.3.AGENTS.END",
        ]
    )
    return "\n".join(lines)


def config_xrlf(name, json_name):
    data = load_json(json_name)
    lines = [f"XRLF.3.CONFIG.{name.upper()}.START", ""]

    def walk(prefix, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}{k} :=")
                    walk(prefix + "  ", v)
                else:
                    lines.append(f"{prefix}{k} := {v}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}[{i}] :=")
                    walk(prefix + "  ", v)
                else:
                    lines.append(f"{prefix}[{i}] := {v}")

    walk("", data)
    lines.extend(["", f"XRLF.3.CONFIG.{name.upper()}.END"])
    return "\n".join(lines)


def update_env():
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        print(f"WARNING: {env_path} not found")
        return
    text = env_path.read_text(encoding="utf-8")
    old_root = "/home/daniel/Lumax/FoveAI"
    new_root = str(WORKSPACE).replace("\\", "/")
    text = text.replace(old_root, new_root)
    env_path.write_text(text, encoding="utf-8")
    print(f"Updated .env XRLF paths to: {new_root}")


def main():
    ensure_dirs()
    write_xrlf(XRLF_DIR / "xrlf.contract.xrlf", contract_xrlf())
    write_xrlf(XRLF_DIR / "holons.xrlf", holons_xrlf())
    write_xrlf(XRLF_DIR / "phasegraph.xrlf", phasegraph_xrlf())
    write_xrlf(XRLF_DIR / "agents.xrlf", agents_xrlf())
    write_xrlf(
        CONFIG_DIR / "geometry.config.xrlf", config_xrlf("geometry", "geometry.json")
    )
    write_xrlf(
        CONFIG_DIR / "resonance.config.xrlf", config_xrlf("resonance", "resonance.json")
    )
    write_xrlf(
        CONFIG_DIR / "thermal.config.xrlf", config_xrlf("thermal", "thermal.json")
    )
    write_xrlf(
        CONFIG_DIR / "runtime.config.xrlf", config_xrlf("runtime", "runtime.json")
    )
    write_xrlf(CONFIG_DIR / "agents.config.xrlf", config_xrlf("agents", "agents.json"))
    update_env()
    print("XRLF workspace bootstrapped at:", WORKSPACE)


if __name__ == "__main__":
    main()
