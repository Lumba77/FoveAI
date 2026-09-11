"""
tests/test_softlayer.py — Unit tests for SoftLayer module and config endpoints
"""
import importlib.util
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from fastapi.testclient import TestClient


@dataclass
class RuntimeState:
    loaded: bool = False
    model_name: str = "test-model"
    n_ctx: int = 4096


class TestSoftLayerEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        runtime_module = ModuleType("runtime.xrlf_runtime")
        runtime_module.XRLFRuntime = RuntimeState
        server_path = Path(__file__).resolve().parents[1] / "api" / "server.py"
        spec = importlib.util.spec_from_file_location("api_softlayer_test_server", server_path)
        assert spec is not None and spec.loader is not None
        server = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"runtime.xrlf_runtime": runtime_module}):
            spec.loader.exec_module(server)
        self.runtime = RuntimeState()
        self.client = TestClient(server.create_app(self.runtime))
        self.addCleanup(self.client.close)

    def test_list_softlayer_configs(self) -> None:
        response = self.client.get("/softlayer")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("modules", data)
        self.assertIn("hud_config", data["modules"])
        self.assertIn("behavior_config", data["modules"])

    def test_get_softlayer_config_file(self) -> None:
        response = self.client.get("/softlayer/hud_config.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/javascript", response.headers.get("content-type", ""))
        self.assertIn("FoveAI", response.text)

    def test_get_nonexistent_config_returns_404(self) -> None:
        response = self.client.get("/softlayer/nonexistent_xyz.js")
        self.assertEqual(response.status_code, 404)

    def test_list_softlayer_modules(self) -> None:
        response = self.client.get("/softlayer/modules")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("modules", data)
        self.assertIn("lighting", data["modules"])
        self.assertIn("sky", data["modules"])
        self.assertIn("particles", data["modules"])

    def test_get_softlayer_module_file(self) -> None:
        response = self.client.get("/softlayer/modules/lighting.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/javascript", response.headers.get("content-type", ""))
        self.assertIn("FoveAI", response.text)

    def test_get_nonexistent_module_returns_404(self) -> None:
        response = self.client.get("/softlayer/modules/nonexistent_xyz.js")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
