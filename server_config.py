"""
FoveAI Server Configuration — Single source of truth for all server host/port settings.

All Python servers should import from here instead of hardcoding addresses:
    from server_config import ServerConfig as cfg
    uvicorn.run(app, host=cfg.BIND_HOST, port=cfg.COMPAGENT_PORT)

This module reads from .env (via python-dotenv) and provides sensible defaults.
It also provides generate_app_config() to auto-generate AppConfig.json for the Quest client.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("foveai.server_config")


# ── Load .env ────────────────────────────────────────────────────────────────
def _load_env_file(path: Path) -> None:
    """Parse a .env file and set os.environ vars (without overwriting existing)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        # Don't overwrite vars already set in the real environment
        if key and key not in os.environ:
            os.environ[key] = val


# Walk up from this file to find the project root .env
_project_root = Path(__file__).resolve().parent
_env_loaded = False
for _ in range(5):
    if (_project_root / ".env").exists():
        _load_env_file(_project_root / ".env")
        _env_loaded = True
        break
    _project_root = _project_root.parent
if not _env_loaded:
    # Fallback: try cwd
    _cwd_env = Path.cwd() / ".env"
    if _cwd_env.exists():
        _load_env_file(_cwd_env)


def _env(key: str, default: str = "") -> str:
    """Read an env var, strip whitespace, return default if empty."""
    val = os.getenv(key, default).strip()
    return val if val else default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except (ValueError, TypeError):
        return default


def detect_lan_ip() -> str:
    """Best-effort primary LAN IP (no traffic is sent — UDP route lookup only)."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.75)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class _ServerAddress:
    def __get__(self, instance: object, owner: type | None = None) -> str:
        return _env("FOVEAI_SERVER_IP") or detect_lan_ip()


def _url_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


class ServerConfig:
    """Central configuration for all FoveAI servers and clients.

    ALL values are read from .env — this module is the reader, not the source of truth.
    To change any port or address, edit .env, then re-run or restart servers.
    The .env file is the single source of truth.
    """

    # ── Network addresses (from .env) ────────────────────────────────────────
    BIND_HOST: str = _env("FOVEAI_BIND_HOST", "0.0.0.0")
    # Client-facing IP. FOVEAI_SERVER_IP wins; otherwise auto-detect the LAN IP
    # so Quest clients get a reachable address instead of a broken 127.0.0.1.
    SERVER_IP = _ServerAddress()

    # ── Unified WebSocket port (from .env) ───────────────────────────────────
    # ALL client traffic goes through this one port: chat, TTS, STT, motor, etc.
    # The IPCServer auto-detects protocol from the first message on /ws.
    WS_PORT: int = _env_int("FOVEAI_WS_PORT", 8400)

    # ── Backend service ports (from .env — separate HTTP services) ───────────
    # Core cognitive servers
    COMPAGENT_PORT: int = _env_int("FOVEAI_COMPAGENT_PORT", 8405)
    SOUL_PORT: int = _env_int("SOUL_PORT", 8405)
    AUTONOMOUS_PORT: int = _env_int("FOVEAI_AUTONOMOUS_PORT", 8410)
    MOTOR_DAEMON_PORT: int = _env_int("FOVEAI_MOTOR_PORT", 8410)
    SUBCONSCIOUS_PORT: int = _env_int("FOVEAI_SUBCONSCIOUS_PORT", 8409)

    # Service servers
    CREATIVE_PORT: int = _env_int("FOVEAI_CREATIVE_PORT", 8412)
    MEMORY_PORT: int = _env_int("FOVEAI_MEMORY_PORT", 8413)
    STT_PORT: int = _env_int("STT_PORT", 8412)
    TTS_PORT: int = _env_int("FOVEAI_TTS_PORT", 8403)
    WEBUI_PORT: int = _env_int("WEBUI_PORT", 8080)
    XRLF_API_PORT: int = _env_int("FOVEAI_XRLF_API_PORT", 8300)

    # ── Derived URLs ─────────────────────────────────────────────────────────
    @classmethod
    def ws_url(cls, port: int, path: str = "/ws") -> str:
        """Build a WebSocket URL using the server IP."""
        return f"ws://{_url_host(cls.SERVER_IP)}:{port}{path}"

    @classmethod
    def http_url(cls, port: int, path: str = "") -> str:
        """Build an HTTP URL using the server IP."""
        return f"http://{_url_host(cls.SERVER_IP)}:{port}{path}"

    @classmethod
    def bind_url(cls, port: int, path: str = "") -> str:
        """Build an HTTP URL using the bind host (for internal/server-side use)."""
        return f"http://{cls.BIND_HOST}:{port}{path}"

    # ── Quest client AppConfig.json ──────────────────────────────────────────
    @classmethod
    def to_app_config(cls, avatar_model: str = "Alicechan.vrm") -> dict:
        """Generate the AppConfig.json dict for the Unity Quest client.
        All traffic goes through one unified WebSocket port."""
        return {
            "serverIp": cls.SERVER_IP,
            "wsPort": cls.WS_PORT,
            "avatarModel": _env("FOVEAI_AVATAR_MODEL", avatar_model),
        }

    @classmethod
    def refresh_network_config(cls, output_path: str | Path) -> dict:
        path = Path(output_path)
        data = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        address = cls.SERVER_IP
        if address == "127.0.0.1" and not _env("FOVEAI_SERVER_IP"):
            return data
        updated = dict(data)
        adb = bool(data.get("use_adb_reverse", data.get("adb_reverse", False)))
        updated.update(
            {
                "version": 1,
                "pc_lan_ip": address,
                "nat_peer_default": address,
                "soul_host": "127.0.0.1" if adb else address,
                "adb_reverse": adb,
                "use_adb_reverse": adb,
            }
        )
        if updated != data:
            path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
        return updated

    @classmethod
    def generate_app_config(
        cls, output_path: str = None, avatar_model: str = "Alicechan.vrm"
    ) -> str:
        """
        Write AppConfig.json for the Quest client.
        Default output: client_quest/Assets/StreamingAssets/AppConfig.json
        Returns the path that was written.
        """
        if output_path is None:
            # Find the client_quest directory relative to this file
            here = Path(__file__).resolve().parent
            candidates = [
                here / "client_quest" / "Assets" / "StreamingAssets" / "AppConfig.json",
                here
                / "FoveAI"
                / "client_quest"
                / "Assets"
                / "StreamingAssets"
                / "AppConfig.json",
                here.parent
                / "client_quest"
                / "Assets"
                / "StreamingAssets"
                / "AppConfig.json",
            ]
            for c in candidates:
                if c.parent.exists():
                    output_path = str(c)
                    break
            if output_path is None:
                output_path = str(here / "AppConfig.json")

        config = cls.to_app_config(avatar_model)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"[ServerConfig] Generated AppConfig.json → {output_path}")
        logger.info(f"[ServerConfig]   serverIp: {cls.SERVER_IP}")
        logger.info(
            f"[ServerConfig]   wsPort: {cls.WS_PORT} (unified WebSocket for all traffic)"
        )
        return output_path

    @classmethod
    def summary(cls) -> str:
        """Return a human-readable summary of all config values."""
        lines = [
            "FoveAI Server Configuration (unified WebSocket):",
            f"  Bind host:    {cls.BIND_HOST}",
            f"  Server IP:    {cls.SERVER_IP}",
            f"  Unified WS:   :{cls.WS_PORT}  (chat, TTS, STT, motor, animation — all on /ws)",
            "  Backend services:",
            f"    :{cls.COMPAGENT_PORT}  compagent/proxy (sovereign core)",
            f"    :{cls.SOUL_PORT}  soul core/XRLF runtime",
            f"    :{cls.MEMORY_PORT}  memory service",
            f"    :{cls.CREATIVE_PORT}  creative service",
            f"    :{cls.STT_PORT}  STT (whisper, standalone)",
            f"    :{cls.MOTOR_DAEMON_PORT}  motor daemon",
            f"    :{cls.SUBCONSCIOUS_PORT}  subconscious daemon",
            f"    :{cls.WEBUI_PORT}  webUI",
            f"    :{cls.XRLF_API_PORT}  XRLF API",
        ]
        return "\n".join(lines)


# ── CLI entry point: generate AppConfig.json ─────────────────────────────────
if __name__ == "__main__":
    import sys

    print(ServerConfig.summary())
    print()

    if "--refresh-network-config" in sys.argv:
        root = Path(__file__).resolve().parent
        for path in (
            root / "foveai_network_config.json",
            root / "Frontend" / "foveai_network_config.json",
        ):
            ServerConfig.refresh_network_config(path)
    elif "--generate-appconfig" in sys.argv:
        path = ServerConfig.generate_app_config()
        print(f"\n✅ AppConfig.json written to: {path}")
    elif "--set-ip" in sys.argv:
        # Quick utility: update FOVEAI_SERVER_IP in .env
        idx = sys.argv.index("--set-ip")
        if idx + 1 < len(sys.argv):
            new_ip = sys.argv[idx + 1]
            print("\n💡 To update your server IP, add this to your .env:")
            print(f"   FOVEAI_SERVER_IP={new_ip}")
            print("   Then run: python server_config.py --generate-appconfig")
        else:
            print("Usage: python server_config.py --set-ip <IP_ADDRESS>")
    else:
        print("\nUsage:")
        print("  python server_config.py                      # Show current config")
        print(
            "  python server_config.py --generate-appconfig # Write AppConfig.json for Quest"
        )
        print(
            "  python server_config.py --set-ip <IP>        # Show instructions to update IP"
        )
