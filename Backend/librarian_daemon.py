import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

# Add paths
FoveAI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, FoveAI_ROOT)
sys.path.insert(0, os.path.join(FoveAI_ROOT, "Mind", "preflight"))
sys.path.insert(0, os.path.join(FoveAI_ROOT, "Body", "XR_Vessel"))


logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("LibrarianDaemon")

FEATURE_INVENTORY_PATH = os.path.join(FoveAI_ROOT, "FEATURE_INVENTORY.md")
FEATURES_INDEX_PATH = os.path.join(FoveAI_ROOT, "user_data", "features_index.json")
NETWORK_CONFIG_PATH = os.path.join(FoveAI_ROOT, "Body", "foveai_network_config.json")


def check_local_services() -> dict:
    """Check health of local ports/services on Windows (SOUL, STT/EARS, MOUTH, WEBUI, VITE, UNSLOTH)."""
    services = {
        "SOUL": 8000,
        "EARS": 8001,
        "MEMORY": 8005,
        "MOUTH": 8004,
        "CREATIVE": 8003,
        "WEBUI": 8080,
        "UNSLOTH": 8888,
    }
    status = {}
    for name, port in services.items():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                res = s.connect_ex(("127.0.0.1", port))
                status[name] = res == 0
        except Exception:
            status[name] = False
    return status


def refresh_network_config() -> None:
    """Auto-detect local IP and update frontend/foveai_network_config.json."""
    try:
        # Get host IP on default route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    data = {
        "version": 1,
        "pc_lan_ip": local_ip,
        "nat_peer_default": local_ip,
        "use_adb_reverse": False,
        "soul_host": local_ip,
        "quest_ip": "",
    }

    # Load existing to preserve custom fields if present
    if os.path.isfile(NETWORK_CONFIG_PATH):
        try:
            with open(NETWORK_CONFIG_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, dict):
                    data.update(existing)
        except Exception:
            pass

    # Ensure local IP is correct
    data["pc_lan_ip"] = local_ip
    data["nat_peer_default"] = local_ip

    # Save network config
    try:
        with open(NETWORK_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write network config: {e}")


def establish_adb_reverse() -> None:
    """Establish ADB reverse tunnels directly on Windows."""
    ports = [8400, 8414, 8402, 8403, 8300, 8001, 8002, 8003, 8004, 8005, 8080, 8888]
    try:
        res = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=5
        )
        if "device" not in res.stdout:
            return

        for p in ports:
            subprocess.run(
                ["adb", "reverse", f"tcp:{p}", f"tcp:{p}"],
                capture_output=True,
                timeout=5,
            )
        logger.info("Sovereign Neural Bridge (ADB Tunnels) established.")
    except Exception:
        pass


def index_features_inventory() -> None:
    """Parse FEATURE_INVENTORY.md and compile to JSON for caching."""
    if not os.path.isfile(FEATURE_INVENTORY_PATH):
        return
    try:
        import feature_inventory_parser as fip

        with open(FEATURE_INVENTORY_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        parsed = fip.parse_feature_inventory_markdown(content)
        parsed["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(FEATURES_INDEX_PATH), exist_ok=True)
        with open(FEATURES_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2)
        logger.info("FEATURE_INVENTORY.md indexed successfully.")
    except Exception as e:
        logger.error(f"Failed to index features inventory: {e}")


def main():
    logger.info("Librarian Daemon started.")
    while True:
        try:
            # 1. Check services
            status = check_local_services()
            logger.info(f"Service status: {status}")

            # 2. Refresh network configuration
            refresh_network_config()

            # 3. Establish ADB reverse tunnels
            establish_adb_reverse()

            # 4. Index features inventory
            index_features_inventory()

            # 5. Clean environment / check for Backend folder
            backend_dir = os.path.join(FoveAI_ROOT, "Backend")
            if os.path.isdir(backend_dir):
                logger.warning(
                    "Architectural principles breach: 'Backend' directory detected in root! Please clean up."
                )

        except Exception as e:
            logger.error(f"Error in daemon loop: {e}")

        time.sleep(60)


if __name__ == "__main__":
    main()
