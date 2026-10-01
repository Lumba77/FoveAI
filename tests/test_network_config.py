import ast
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server_config
from server_config import ServerConfig


class TestNetworkConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"FOVEAI_SERVER_IP": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_address_tracks_dhcp_changes(self) -> None:
        for address in ("192.0.2.10", "192.0.2.20"):
            with (
                self.subTest(address=address),
                patch.object(server_config, "detect_lan_ip", return_value=address),
            ):
                self.assertEqual(ServerConfig.SERVER_IP, address)
                self.assertEqual(ServerConfig.to_app_config()["serverIp"], address)
                self.assertEqual(ServerConfig.ws_url(8403), f"ws://{address}:8403/ws")

    def test_explicit_hostname_override(self) -> None:
        with patch.dict(os.environ, {"FOVEAI_SERVER_IP": "foveai.local"}):
            self.assertEqual(ServerConfig.http_url(8400), "http://foveai.local:8400")

    def test_ipv6_url(self) -> None:
        with patch.dict(os.environ, {"FOVEAI_SERVER_IP": "2001:db8::10"}):
            self.assertEqual(ServerConfig.ws_url(8403), "ws://[2001:db8::10]:8403/ws")

    def test_refresh_preserves_client_settings_and_adb_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.json"
            for adb in (False, True):
                path.write_text(
                    json.dumps(
                        {
                            "pc_lan_ip": "192.0.2.10",
                            "soul_host": "192.0.2.10",
                            "quest_ip": "192.0.2.30",
                            "use_adb_reverse": adb,
                            "custom": 7,
                        }
                    )
                )
                with patch.object(
                    server_config, "detect_lan_ip", return_value="192.0.2.20"
                ):
                    ServerConfig.refresh_network_config(path)
                data = json.loads(path.read_text())
                self.assertEqual(data["pc_lan_ip"], "192.0.2.20")
                self.assertEqual(data["nat_peer_default"], "192.0.2.20")
                self.assertEqual(
                    data["soul_host"], "127.0.0.1" if adb else "192.0.2.20"
                )
                self.assertEqual(data["quest_ip"], "192.0.2.30")
                self.assertEqual(data["custom"], 7)

    def test_offline_refresh_preserves_previous_lan_address(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.json"
            original = '{"pc_lan_ip": "192.0.2.10"}'
            path.write_text(original)
            with patch.object(server_config, "detect_lan_ip", return_value="127.0.0.1"):
                ServerConfig.refresh_network_config(path)
            self.assertEqual(path.read_text(), original)

    def test_failed_detection_closes_socket(self) -> None:
        with patch.object(socket, "socket") as factory:
            factory.return_value.__enter__.return_value.connect.side_effect = OSError(
                "offline"
            )
            self.assertEqual(server_config.detect_lan_ip(), "127.0.0.1")
            factory.return_value.__exit__.assert_called_once()

    def test_sentry_refreshes_stale_cache_but_preserves_docker_address(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "Backend" / "autonomous_sentry.py"
        )
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        functions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name
            in ("refresh_quest_network_config", "_network_config_canonical_json")
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.json"
            namespace = {
                "os": os,
                "json": json,
                "logger": server_config.logger,
                "QUEST_NETWORK_CONFIG": str(path),
                "_auto_pc_lan_ipv4": lambda: "192.0.2.20",
                "_in_docker": lambda: False,
            }
            exec(
                compile(
                    ast.Module(body=functions, type_ignores=[]), str(source), "exec"
                ),
                namespace,
            )
            with patch.dict(
                os.environ,
                {
                    "FoveAI_PC_LAN_IP": "",
                    "FoveAI_QUEST_LINK_MODE": "lan",
                    "FoveAI_USE_ADB_REVERSE": "",
                },
            ):
                path.write_text(
                    json.dumps(
                        {"pc_lan_ip": "192.0.2.10", "nat_peer_default": "192.0.2.10"}
                    )
                )
                namespace["refresh_quest_network_config"]("")
                self.assertEqual(
                    json.loads(path.read_text())["pc_lan_ip"], "192.0.2.20"
                )
                namespace["_auto_pc_lan_ipv4"] = lambda: ""
                namespace["_in_docker"] = lambda: True
                namespace["refresh_quest_network_config"]("")
                self.assertEqual(
                    json.loads(path.read_text())["pc_lan_ip"], "192.0.2.20"
                )


if __name__ == "__main__":
    unittest.main()
