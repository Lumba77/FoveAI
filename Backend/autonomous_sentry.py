import json
import logging
import os
import socket
import subprocess
import time
from datetime import datetime, timezone

import httpx
from preflight.agentic_solver import (
    answer_runtime_question,
    propose_actions,
    propose_architecture_plan,
    read_unstable_features,
)
from preflight.checks import run_preflight, summarize
from preflight.json_util import load_playbook_path

# Default WARNING: routine chatter at DEBUG. Override with FoveAI_SENTRY_LOG_LEVEL=INFO for verbose loops.
_sentry_lvl_name = os.getenv("FoveAI_SENTRY_LOG_LEVEL", "WARNING").upper()
_sentry_lvl = getattr(logging, _sentry_lvl_name, logging.WARNING)
logging.basicConfig(level=_sentry_lvl, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("AutonomousSentry")
logger.setLevel(_sentry_lvl)


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default)).strip().lower()
    return v in ("1", "true", "yes", "on")


# Same file connect_quest.ps1 writes (repo mounted at /app). Sentry refreshes quest_ip + reverses.
QUEST_NETWORK_CONFIG = os.getenv(
    "FoveAI_NETWORK_CONFIG_PATH",
    os.path.join("/app", "Godot", "foveai_network_config.json"),
)


def _in_docker() -> bool:
    return os.path.isfile("/.dockerenv")


def _is_docker_bridge_ipv4(ip: str) -> bool:
    """Typical Linux bridge client address (172.17–172.31.x.x) — not the PC Wi‑Fi IP for Quest."""
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return a == 172 and 16 <= b <= 31


def _auto_pc_lan_ipv4() -> str:
    """Outbound IPv4 on the default route — matches the PC LAN for Quest when sentry runs on the host.

    Inside Docker, the UDP trick usually yields the container bridge (172.x), not your Wi‑Fi address,
    so we skip auto there; use FoveAI_PC_LAN_IP or run connect_quest.ps1 on the host instead.
    """
    if _in_docker():
        return ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.75)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        return ""
    if not ip or ip.startswith("127.") or ip.startswith("169.254."):
        return ""
    if _is_docker_bridge_ipv4(ip):
        return ""
    return ip


def _service_health_urls() -> dict[str, str]:
    """
    Heartbeat targets. Defaults use Docker DNS names; override with full URLs or SOUL_URL/EARS_URL when
    running the sentry on the host (http://127.0.0.1:8000/...). Long /compagent work can block the Soul
    process's event loop (sync local inference), so health probes need a generous timeout — see
    FoveAI_SENTRY_HEALTH_TIMEOUT_SEC.
    """
    soul_base = os.getenv("SOUL_URL", "http://foveai_soul:8402").strip().rstrip("/")
    ears_base = os.getenv("EARS_URL", "http://foveai_body:8001").strip().rstrip("/")
    mouth_base = (
        os.getenv("MOUTH_URL", os.getenv("FoveAI_MOUTH_URL", "http://foveai_body:8002"))
        .strip()
        .rstrip("/")
    )
    turbo_base = (
        os.getenv(
            "TURBO_URL", os.getenv("FoveAI_TURBO_URL", "http://foveai_turbochat:8005")
        )
        .strip()
        .rstrip("/")
    )
    creative_base = (
        os.getenv(
            "CREATIVE_SERVICE_URL",
            "http://foveai_creativity:8003",
        )
        .strip()
        .rstrip("/")
    )
    urls: dict[str, str] = {
        "SOUL": os.getenv("FoveAI_SENTRY_SOUL_HEALTH_URL", f"{soul_base}/health"),
        "EARS": os.getenv("FoveAI_SENTRY_EARS_HEALTH_URL", f"{ears_base}/health"),
        "MOUTH": os.getenv("FoveAI_SENTRY_MOUTH_HEALTH_URL", f"{mouth_base}/health"),
    }
    # Turbo health is only relevant when mouth backend is turbo.
    tts_backend = _resolved_tts_backend()
    if tts_backend == "turbo":
        urls["TURBO"] = os.getenv(
            "FoveAI_SENTRY_TURBO_HEALTH_URL", f"{turbo_base}/health"
        )
    # Creativity (dream) on :8003 — foveai_embers does not publish host ports; conflict on 8003 is never from embers.
    if _bool_env("FoveAI_SENTRY_CHECK_CREATIVITY", True):
        cu = os.getenv("FoveAI_SENTRY_CREATIVITY_HEALTH_URL", "").strip()
        if cu:
            urls["CREATIVE"] = cu
        elif creative_base:
            urls["CREATIVE"] = f"{creative_base}/health"
    # Same container as uvicorn (127.0.0.1); detects dead Web UI while sentry still runs.
    if _bool_env("FoveAI_SENTRY_CHECK_WEBUI", True):
        wu = os.getenv(
            "FoveAI_SENTRY_WEBUI_HEALTH_URL", "http://127.0.0.1:8080/health"
        ).strip()
        if wu:
            urls["WEBUI"] = wu
    # Autonomous Core (Jen's independent runtime) on :8010
    if _bool_env("FoveAI_SENTRY_CHECK_AUTONOMOUS", True):
        au = os.getenv(
            "FoveAI_SENTRY_AUTONOMOUS_HEALTH_URL", "http://127.0.0.1:8010/health"
        ).strip()
        if au:
            urls["AUTONOMOUS"] = au
    return urls


def _resolved_tts_backend() -> str:
    """
    Active mouth stack: turbo or chatterbox.
    Source order: marker file first, then env, then turbo.
    """
    marker = os.getenv(
        "FoveAI_TTS_BACKEND_FILE", "/app/Backend/preflight/tts_backend"
    ).strip()
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


# Resolved once at import; callers may re-read via _service_health_urls() in tests.
SERVICES: dict[str, str] = _service_health_urls()

OUTBOX_DIR = os.getenv(
    "FoveAI_SENTRY_OUTBOX_DIR", os.path.join("/app", "Backend", "preflight", "outbox")
)
WATCHDOG_POLICY_PATH = os.getenv(
    "FoveAI_SENTRY_WATCHDOG_POLICY_PATH",
    os.path.join("/app", "ops", "playbooks", "watchdog_policy.json"),
)
INBOX_DIR = os.getenv(
    "FoveAI_SENTRY_INBOX_DIR", os.path.join("/app", "Backend", "preflight", "inbox")
)

# foveai_ops mounts /var/run/docker.sock; COMPOSE_PROJECT_NAME should match host `docker compose ls`.
_COMPOSE_FILE = "/app/docker-compose.yml"


def _docker_compose_argv() -> list[str]:
    return ["docker", "compose", "-f", _COMPOSE_FILE]


def _run_docker_compose(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        _docker_compose_argv() + args,
        cwd="/app",
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _docker_restart(
    container: str, timeout: float = 40.0
) -> subprocess.CompletedProcess:
    """Restart by container name — avoids compose project mismatch when cwd is /app."""
    return subprocess.run(
        ["docker", "restart", container],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _network_config_canonical_json(data: dict) -> str:
    """Stable string for equality (key order independent)."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def _gpu_guard_may_skip_approval(solver_decision: dict) -> bool:
    """GPU watchdog remediations are destructive; allow auto-run only when explicitly enabled."""
    if solver_decision.get("reason") != "gpu-guard":
        return False
    return _bool_env("FoveAI_SENTRY_GPU_GUARD_ALLOW_AUTO_REMEDIATE", True)


def _load_watchdog_policy() -> dict:
    default = {
        "inspect": {"containers": True, "logs": True},
        "actions": {
            "allow_docker_compose_up": True,
            "allow_bridge_reverse": True,
            "allow_service_restart": False,
            "allow_preflight_level_switch": True,
            "allow_extended_test_probe": True,
            "allow_architect_escalation": True,
        },
        "approval_required_actions": [
            "docker_compose_up",
            "restart_service_soul",
            "restart_service_body",
            "restart_service_turbo",
            "restart_service_ops",
            "rebuild_service_soul",
        ],
    }
    try:
        if os.path.isfile(WATCHDOG_POLICY_PATH):
            data = load_playbook_path(WATCHDOG_POLICY_PATH, encoding="utf-8-sig")
            if isinstance(data, dict):
                default.update(data)
    except Exception as e:
        logger.warning("Could not load watchdog policy: %s", e)
    return default


def _write_outbox(name: str, payload: dict) -> None:
    try:
        os.makedirs(OUTBOX_DIR, exist_ok=True)
        path = os.path.join(OUTBOX_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        logger.debug("📮 Outbox update: %s", path)
    except Exception as e:
        logger.warning("Could not write outbox item %s: %s", name, e)


def _probe_soul_gpu_offload() -> dict:
    """
    Runtime probe for llama-cpp GPU capability inside foveai_soul.
    This catches silent CPU-only wheel/runtime regressions.
    """
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "supports_gpu_offload": None,
        "container": "foveai_soul",
        "error": "",
    }
    cmd = [
        "docker",
        "exec",
        "foveai_soul",
        "python",
        "-c",
        "import llama_cpp; print(llama_cpp.llama_cpp.llama_supports_gpu_offload())",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        out = (res.stdout or "").strip().lower()
        if res.returncode != 0:
            report["error"] = ((res.stderr or "") + " " + out).strip()[:400]
        else:
            if out == "true":
                report["ok"] = True
                report["supports_gpu_offload"] = True
            elif out == "false":
                report["ok"] = False
                report["supports_gpu_offload"] = False
                report["error"] = "llama-cpp runtime reports GPU offload unsupported"
            else:
                report["error"] = f"unexpected probe output: {out[:120]}"
    except Exception as e:
        report["error"] = f"probe exception: {e}"
    _write_outbox("soul_runtime_mode_latest.json", report)
    return report


def _read_json_file(path: str) -> dict | None:
    try:
        if not os.path.isfile(path):
            return None
        # Accept UTF-8 with or without BOM (PowerShell Set-Content often writes BOM).
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("Could not parse JSON file %s: %s", path, e)
        return None


def _archive_processed_inbox(path: str) -> None:
    try:
        done_dir = os.path.join(INBOX_DIR, "processed")
        os.makedirs(done_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = os.path.basename(path)
        target = os.path.join(done_dir, f"{ts}_{base}")
        os.replace(path, target)
    except Exception as e:
        logger.warning("Could not archive inbox item %s: %s", path, e)


def _speak_watchdog_answer(question: str, answer: str) -> None:
    if not _bool_env("FoveAI_SENTRY_SPEAK_ANSWERS", False):
        return
    tts_url = os.getenv("FoveAI_SENTRY_TTS_URL", "http://foveai_body:8002/tts").strip()
    voice = os.getenv("FoveAI_SENTRY_TTS_VOICE", "female_american1-lumba").strip()
    engine = os.getenv("FoveAI_SENTRY_TTS_ENGINE", "TURBO").strip()
    max_chars = int(os.getenv("FoveAI_SENTRY_TTS_MAX_CHARS", "320"))
    # Keep spoken output short and useful.
    spoken = f"Watchdog answer for question: {question}. {answer}".replace(
        "\n", " "
    ).strip()
    if len(spoken) > max_chars:
        spoken = spoken[: max_chars - 3].rstrip() + "..."
    payload = {"text": spoken, "voice": voice, "engine": engine}
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(tts_url, json=payload)
            if resp.status_code == 200:
                logger.debug(
                    "🔊 Watchdog TTS answer spoken via %s (%s)", tts_url, engine
                )
            else:
                logger.warning(
                    "Watchdog TTS failed: status=%s body=%s",
                    resp.status_code,
                    (resp.text or "")[:180],
                )
    except Exception as e:
        logger.warning("Watchdog TTS request failed: %s", e)


def _request_approval(reason: str, actions: list[str], context: dict) -> None:
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "requested_actions": actions,
        "context": context,
        "status": "awaiting_user_approval",
    }
    _write_outbox("approval_request_latest.json", payload)


def _inspect_containers_report() -> dict:
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "docker_ps": "",
        "service_inspect": {},
        "recent_logs": {},
    }
    service_to_container = {
        "SOUL": "foveai_soul",
        "EARS": "foveai_body",
        "MOUTH": "foveai_body",
        "TURBO": "foveai_turbochat",
        "OPS": "foveai_ops",
    }
    try:
        ps = subprocess.run(
            ["docker", "ps"], capture_output=True, text=True, timeout=20
        )
        report["docker_ps"] = (ps.stdout or ps.stderr or "").strip()
    except Exception as e:
        report["docker_ps"] = f"docker ps failed: {e}"
    for key, cname in service_to_container.items():
        try:
            ins = subprocess.run(
                ["docker", "inspect", cname], capture_output=True, text=True, timeout=20
            )
            report["service_inspect"][key] = (ins.stdout or ins.stderr or "")[:6000]
        except Exception as e:
            report["service_inspect"][key] = f"inspect failed: {e}"
        try:
            logs = subprocess.run(
                ["docker", "logs", "--tail", "120", cname],
                capture_output=True,
                text=True,
                timeout=20,
            )
            report["recent_logs"][key] = (
                (logs.stdout or "") + "\n" + (logs.stderr or "")
            ).strip()[:9000]
        except Exception as e:
            report["recent_logs"][key] = f"logs failed: {e}"
    _write_outbox("container_watchdog_report_latest.json", report)
    return report


def _handle_investigation_questions(failures: dict) -> None:
    os.makedirs(INBOX_DIR, exist_ok=True)
    question_path = os.path.join(INBOX_DIR, "question_latest.json")
    payload = _read_json_file(question_path)
    if not payload:
        return
    question = str(payload.get("question", "")).strip()
    if not question:
        _archive_processed_inbox(question_path)
        return
    context = {
        "failures": failures,
        "policy_path": WATCHDOG_POLICY_PATH,
        "inspect_report": _inspect_containers_report(),
        "question_meta": payload,
    }
    answer = answer_runtime_question(question=question, context=context)
    _write_outbox(
        "question_answer_latest.json",
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "answer": answer,
        },
    )
    _speak_watchdog_answer(question=question, answer=answer)
    _archive_processed_inbox(question_path)


def _action_needs_approval(action: str, policy: dict) -> bool:
    required = policy.get("approval_required_actions", [])
    return isinstance(required, list) and action in required


def _action_allowed(action: str, policy: dict) -> bool:
    actions = policy.get("actions", {})
    if action == "docker_compose_up":
        return bool(actions.get("allow_docker_compose_up", False))
    if action == "bridge_reverse":
        return bool(actions.get("allow_bridge_reverse", True))
    if action in (
        "restart_service_soul",
        "restart_service_body",
        "restart_service_turbo",
        "restart_service_ops",
    ):
        return bool(actions.get("allow_service_restart", False))
    if action == "rebuild_service_soul":
        # Rebuild requires compose build/up permissions.
        return bool(actions.get("allow_docker_compose_up", False))
    if action in ("preflight_standard", "preflight_deep"):
        return bool(actions.get("allow_preflight_level_switch", True))
    if action == "extended_test_probe":
        return bool(actions.get("allow_extended_test_probe", True))
    if action == "request_architecture_plan":
        return bool(actions.get("allow_architect_escalation", True))
    if action == "inspect_containers":
        return bool(policy.get("inspect", {}).get("containers", True))
    if action == "capture_service_logs":
        return bool(policy.get("inspect", {}).get("logs", True))
    return True


def check_services() -> dict:
    logger.debug("--- Sentry Pulse: Checking Heartbeats ---")
    failures = {}
    urls = _service_health_urls()
    try:
        timeout_sec = float(os.getenv("FoveAI_SENTRY_HEALTH_TIMEOUT_SEC", "25"))
    except ValueError:
        timeout_sec = 25.0
    timeout_sec = max(5.0, min(timeout_sec, 120.0))
    for name, url in urls.items():
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    logger.debug("✅ %s: ONLINE", name)
                    failures[name] = False
                else:
                    logger.warning(
                        "⚠️ %s: UNSTABLE (Status %s) url=%s", name, resp.status_code, url
                    )
                    failures[name] = True
        except Exception as e:
            err = str(e)
            hint = ""
            if name == "SOUL" and (
                "timed out" in err.lower() or "timeout" in err.lower()
            ):
                hint = (
                    " — Soul may still be running: long /compagent + sync local inference can block /health "
                    "on one uvicorn worker; raise FoveAI_SENTRY_HEALTH_TIMEOUT_SEC or run compagent with "
                    "non-blocking generation."
                )
            logger.error("❌ %s: OFFLINE (%s) url=%s%s", name, err, url, hint)
            failures[name] = True
    return failures


def _parse_quest_ip_from_adb_devices(stdout: str) -> str:
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or "\t" not in line:
            continue
        serial, state = line.split("\t", 1)
        serial = serial.strip()
        if state.strip() != "device":
            continue
        if ":" in serial:
            host = serial.split(":", 1)[0].strip()
            parts = host.split(".")
            if len(parts) == 4 and all(
                p.isdigit() and 0 <= int(p) <= 255 for p in parts
            ):
                return host
    return ""


def refresh_quest_network_config(quest_ip: str) -> None:
    """Merge NAT / peer defaults; pc_lan_ip from FoveAI_PC_LAN_IP, JSON file, or host auto-detect (non-Docker)."""
    data: dict = {}
    if os.path.isfile(QUEST_NETWORK_CONFIG):
        try:
            with open(QUEST_NETWORK_CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception as e:
            logger.debug("Could not read %s: %s", QUEST_NETWORK_CONFIG, e)
            data = {}

    env_lan = (
        os.getenv("FoveAI_PC_LAN_IP", "").strip()
        or os.getenv("FOVEAI_SERVER_IP", "").strip()
    )
    if env_lan:
        data["pc_lan_ip"] = env_lan
        data["nat_peer_default"] = env_lan
    else:
        existing = str(data.get("pc_lan_ip", "") or "").strip()
        auto = _auto_pc_lan_ipv4()
        if auto:
            data["pc_lan_ip"] = auto
            data["nat_peer_default"] = auto
        elif not existing and _in_docker():
            logger.debug(
                "Quest LAN: pc_lan_ip missing (FoveAI_PC_LAN_IP unset, empty %s). "
                "Set FoveAI_PC_LAN_IP in .env or run .\\connect_quest.ps1 on Windows to write the JSON.",
                QUEST_NETWORK_CONFIG,
            )
    if quest_ip:
        data["quest_ip"] = quest_ip
    mode_env = (
        os.getenv("FoveAI_QUEST_LINK_MODE", "").strip().lower()
    )  # adb | lan | auto
    use_adb_env = os.getenv("FoveAI_USE_ADB_REVERSE", "").strip().lower()
    if mode_env == "adb":
        desired_adb_reverse = True
    elif mode_env == "lan":
        desired_adb_reverse = False
    elif use_adb_env in ("1", "true", "yes", "on"):
        desired_adb_reverse = True
    elif use_adb_env in ("0", "false", "no", "off"):
        desired_adb_reverse = False
    else:
        # Preserve current choice from file when not explicitly overridden.
        desired_adb_reverse = bool(data.get("use_adb_reverse", True))

    data["version"] = 1
    data["adb_reverse"] = bool(desired_adb_reverse)
    data["use_adb_reverse"] = bool(desired_adb_reverse)
    if desired_adb_reverse:
        data["soul_host"] = "127.0.0.1"
    elif data.get("pc_lan_ip"):
        data["soul_host"] = data["pc_lan_ip"]
    if "nat_peer_default" not in data or not data.get("nat_peer_default"):
        if data.get("pc_lan_ip"):
            data["nat_peer_default"] = data["pc_lan_ip"]

    try:
        parent = os.path.dirname(QUEST_NETWORK_CONFIG)
        if parent:
            os.makedirs(parent, exist_ok=True)
        new_canon = _network_config_canonical_json(data)
        if os.path.isfile(QUEST_NETWORK_CONFIG):
            try:
                with open(QUEST_NETWORK_CONFIG, "r", encoding="utf-8-sig") as f:
                    old_data = json.load(f)
                if (
                    isinstance(old_data, dict)
                    and _network_config_canonical_json(old_data) == new_canon
                ):
                    return
            except Exception:
                pass
        with open(QUEST_NETWORK_CONFIG, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        logger.debug(
            "Updated %s (quest_ip=%s)", QUEST_NETWORK_CONFIG, quest_ip or "(unchanged)"
        )
    except Exception as e:
        logger.warning("Could not write %s: %s", QUEST_NETWORK_CONFIG, e)


def establish_neural_bridge():
    if not _bool_env("FoveAI_SENTRY_REFRESH_NETWORK_CONFIG", True):
        logger.debug(
            "Sentry bridge: FoveAI_SENTRY_REFRESH_NETWORK_CONFIG=0 — skipping Quest network file / adb reverse."
        )
        return
    mode_env = os.getenv("FoveAI_QUEST_LINK_MODE", "").strip().lower()
    use_adb_env = os.getenv("FoveAI_USE_ADB_REVERSE", "").strip().lower()
    if mode_env == "lan" or use_adb_env in ("0", "false", "no", "off"):
        # In LAN mode we intentionally avoid adb reverse and port tunnel churn.
        refresh_quest_network_config("")
        logger.debug("LAN mode: bridge metadata sync (no adb reverse).")
        return
    logger.debug("--- Sovereign Bridge: Heartbeat (ADB Tunnels) ---")
    # All essential ports for Jen's Manifestation and Brain connectivity (match connect_quest.ps1 / push_all.ps1)
    ports = [8000, 8001, 8002, 8003, 8004, 8005, 8006, 8020, 8080, 6006, 6007, 6379]

    # Verify we can even reach the host ADB server first
    try:
        # Check if any devices are even connected to the host
        res = subprocess.run(
            ["adb", "-H", "host.docker.internal", "devices"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if "device" not in res.stdout:
            logger.warning(
                "⚠️ No Quest 3 detected via host.docker.internal. Ensure USB is plugged in!"
            )
            return

        quest_ip = _parse_quest_ip_from_adb_devices(res.stdout)
        refresh_quest_network_config(quest_ip)

        for p in ports:
            # -H host.docker.internal bridges the container to the Windows Host's ADB daemon
            cmd = [
                "adb",
                "-H",
                "host.docker.internal",
                "reverse",
                f"tcp:{p}",
                f"tcp:{p}",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0:
                logger.debug(f"✅ Bridge TCP:{p} locked.")
            else:
                # If reverse already exists, we skip the warning to avoid log spam
                pass
        logger.debug("✅ Sovereign Bridge: All tunnels SECURE.")
    except Exception as e:
        logger.error(f"❌ Bridge Failure: {e!s}")


def _execute_heal_actions(
    actions: list[str], policy: dict, failures: dict, solver_decision: dict
) -> None:
    for action in actions:
        if not _action_allowed(action, policy):
            logger.warning("🛡️ Action blocked by watchdog policy: %s", action)
            continue
        if _action_needs_approval(action, policy) and not _gpu_guard_may_skip_approval(
            solver_decision
        ):
            _request_approval(
                reason=f"approval-required:{action}",
                actions=[action],
                context={"failures": failures, "solver_decision": solver_decision},
            )
            logger.warning("Approval queued: %s", action)
            continue
        if action == "docker_compose_up":
            try:
                res = _run_docker_compose(["up", "-d"], timeout=45)
                if res.returncode == 0:
                    logger.debug("🛠️ Heal action docker_compose_up: OK")
                else:
                    logger.warning(
                        "🛠️ Heal action docker_compose_up failed: %s",
                        (res.stderr or "").strip(),
                    )
            except Exception as e:
                logger.warning("🛠️ Heal action docker_compose_up error: %s", e)
        elif action == "bridge_reverse":
            logger.debug("🛠️ Heal action bridge_reverse")
            establish_neural_bridge()
        elif action == "recheck_services":
            logger.debug("🛠️ Heal action recheck_services")
            check_services()
        elif action == "sleep_short":
            time.sleep(2)
        elif action == "refresh_network_config":
            refresh_quest_network_config("")
        elif action == "preflight_standard":
            pf = run_preflight(level="standard", autoheal=True)
            logger.debug("🧪 Preflight(standard): %s", summarize(pf))
        elif action == "preflight_deep":
            pf = run_preflight(level="deep", autoheal=True)
            logger.debug("🧪 Preflight(deep): %s", summarize(pf))
        elif action == "restart_service_soul":
            res = _docker_restart("foveai_soul")
            logger.debug("🛠️ restart_service_soul rc=%s", res.returncode)
        elif action == "restart_service_body":
            res = _docker_restart("foveai_body")
            logger.debug("🛠️ restart_service_body rc=%s", res.returncode)
        elif action == "restart_service_turbo":
            res = _docker_restart("foveai_turbochat")
            logger.debug("🛠️ restart_service_turbo rc=%s", res.returncode)
        elif action == "restart_service_ops":
            res = _docker_restart("foveai_ops")
            logger.debug("🛠️ restart_service_ops rc=%s", res.returncode)
        elif action == "rebuild_service_soul":
            try:
                build = _run_docker_compose(["build", "foveai_soul"], timeout=1800)
                if build.returncode != 0:
                    logger.warning(
                        "🛠️ rebuild_service_soul build failed: %s",
                        (build.stderr or "").strip()[:300],
                    )
                    continue
                up = _run_docker_compose(
                    ["up", "-d", "--force-recreate", "foveai_soul"], timeout=240
                )
                logger.debug("🛠️ rebuild_service_soul up rc=%s", up.returncode)
                if up.returncode != 0:
                    logger.warning(
                        "🛠️ rebuild_service_soul up failed: %s",
                        (up.stderr or "").strip()[:300],
                    )
            except Exception as e:
                logger.warning("🛠️ rebuild_service_soul error: %s", e)
        elif action == "inspect_containers" or action == "capture_service_logs":
            _inspect_containers_report()
        elif action == "extended_test_probe":
            probe = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "health_endpoints": _service_health_urls(),
                "note": "Extend with feature-specific probes over time.",
            }
            _write_outbox("extended_test_probe_latest.json", probe)
        elif action == "request_architecture_plan":
            plan = propose_architecture_plan(
                failures=failures, solver_decision=solver_decision
            )
            _write_outbox("architect_plan_latest.json", plan)
            _request_approval(
                reason="architect-plan-generated",
                actions=["review_architect_plan"],
                context={"architect_plan_file": "architect_plan_latest.json"},
            )
        elif action == "none":
            logger.debug("🛠️ Heal action none")
        else:
            logger.warning("🛠️ Unknown heal action ignored: %s", action)


if __name__ == "__main__":
    preflight_level = os.getenv("FoveAI_PREFLIGHT_LEVEL", "light").strip().lower()
    preflight_autoheal = os.getenv(
        "FoveAI_PREFLIGHT_AUTOHEAL", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
    sentry_interval_sec = float(os.getenv("FoveAI_SENTRY_INTERVAL_SEC", "15"))
    roam_enabled = _bool_env("FoveAI_SENTRY_ROAM_ENABLED", True)
    roam_when_in_service = _bool_env("FoveAI_SENTRY_ROAM_WHEN_IN_SERVICE", True)
    roam_when_not_in_service = _bool_env("FoveAI_SENTRY_ROAM_WHEN_NOT_IN_SERVICE", True)
    roam_min_interval_sec = float(
        os.getenv("FoveAI_SENTRY_ROAM_MIN_INTERVAL_SEC", "60")
    )
    roam_loop_budget_ms = float(os.getenv("FoveAI_SENTRY_ROAM_LOOP_BUDGET_MS", "700"))
    gpu_guard_enabled = _bool_env("FoveAI_SENTRY_SOUL_GPU_GUARD_ENABLED", True)
    gpu_guard_hold_loops = max(
        1, int(os.getenv("FoveAI_SENTRY_SOUL_GPU_GUARD_HOLD_LOOPS", "2"))
    )
    gpu_guard_cooldown_sec = max(
        30.0, float(os.getenv("FoveAI_SENTRY_SOUL_GPU_GUARD_COOLDOWN_SEC", "1800"))
    )
    gpu_guard_remediation = (
        os.getenv("FoveAI_SENTRY_SOUL_GPU_GUARD_REMEDIATION", "rebuild").strip().lower()
    )
    gpu_guard_bad_loops = 0
    last_gpu_guard_fix_ts = 0.0
    last_roam_ts = 0.0
    policy = _load_watchdog_policy()
    print(
        "[AutonomousSentry] started — further console output: warnings/errors only "
        f"(FoveAI_SENTRY_LOG_LEVEL={_sentry_lvl_name}, interval={sentry_interval_sec}s)",
        flush=True,
    )
    while True:
        loop_start = time.time()
        try:
            pf = run_preflight(level=preflight_level, autoheal=preflight_autoheal)
            logger.debug("🧪 Preflight(%s): %s", preflight_level, summarize(pf))
        except Exception as e:
            logger.warning("Preflight execution failed: %s", e)
        failures = check_services()
        if preflight_autoheal and any(failures.values()):
            unstable_features = read_unstable_features()
            decision = propose_actions(failures, unstable_features=unstable_features)
            actions = decision.get("actions", ["none"])
            reason = decision.get("reason", "")
            logger.debug("🤖 Agentic decision: actions=%s reason=%s", actions, reason)
            if decision.get("request_approval", False):
                _request_approval(
                    reason=reason or "solver-requested-approval",
                    actions=actions if isinstance(actions, list) else ["none"],
                    context={"failures": failures, "decision": decision},
                )
            if isinstance(actions, list):
                _execute_heal_actions(
                    actions, policy=policy, failures=failures, solver_decision=decision
                )
            improvement_notes = decision.get("improvement_notes", [])
            test_measures = decision.get("test_measures", [])
            if improvement_notes or test_measures:
                _write_outbox(
                    "improvement_suggestions_latest.json",
                    {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "improvement_notes": improvement_notes,
                        "test_measures": test_measures,
                        "failures": failures,
                    },
                )
        _handle_investigation_questions(failures)

        # Dedicated runtime guard: health can be green even when soul silently runs CPU-only.
        if gpu_guard_enabled and not failures.get("SOUL", False):
            probe = _probe_soul_gpu_offload()
            if probe.get("supports_gpu_offload") is False:
                gpu_guard_bad_loops += 1
                logger.warning(
                    "⚠️ Soul GPU guard: GPU offload unavailable (%s/%s loops)",
                    gpu_guard_bad_loops,
                    gpu_guard_hold_loops,
                )
                _write_outbox(
                    "soul_gpu_guard_alert_latest.json",
                    {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "status": "degraded_cpu_only",
                        "bad_loops": gpu_guard_bad_loops,
                        "hold_loops": gpu_guard_hold_loops,
                        "remediation": gpu_guard_remediation,
                        "probe": probe,
                    },
                )
                cooldown_ok = (
                    time.time() - last_gpu_guard_fix_ts
                ) >= gpu_guard_cooldown_sec
                if gpu_guard_bad_loops >= gpu_guard_hold_loops and cooldown_ok:
                    if gpu_guard_remediation == "restart":
                        _execute_heal_actions(
                            ["restart_service_soul"],
                            policy=policy,
                            failures=failures,
                            solver_decision={"reason": "gpu-guard"},
                        )
                        last_gpu_guard_fix_ts = time.time()
                    elif gpu_guard_remediation == "rebuild":
                        _execute_heal_actions(
                            ["rebuild_service_soul"],
                            policy=policy,
                            failures=failures,
                            solver_decision={"reason": "gpu-guard"},
                        )
                        last_gpu_guard_fix_ts = time.time()
                    else:
                        logger.debug(
                            "Soul GPU guard remediation disabled (mode=%s)",
                            gpu_guard_remediation,
                        )
                    gpu_guard_bad_loops = 0
            else:
                gpu_guard_bad_loops = 0

        # Shepherd roaming: periodic inside-view inspection.
        # - If app is not in service: always allowed (when enabled).
        # - If app is in service: only when loop overhead is below budget.
        loop_elapsed_ms = (time.time() - loop_start) * 1000.0
        app_in_service = not any(failures.values())
        now = time.time()
        roam_due = (now - last_roam_ts) >= max(5.0, roam_min_interval_sec)
        allow_roam = False
        if roam_enabled and roam_due:
            if (
                app_in_service
                and roam_when_in_service
                and loop_elapsed_ms <= roam_loop_budget_ms
            ):
                allow_roam = True
            if (not app_in_service) and roam_when_not_in_service:
                allow_roam = True
        if allow_roam or _bool_env("FoveAI_SENTRY_INSPECT_ALWAYS", False):
            _inspect_containers_report()
            last_roam_ts = now

        establish_neural_bridge()
        time.sleep(max(1.0, sentry_interval_sec))
