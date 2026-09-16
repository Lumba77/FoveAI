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


class TestAPIHealth(unittest.TestCase):
    def setUp(self) -> None:
        runtime_module = ModuleType("runtime.xrlf_runtime")
        runtime_module.XRLFRuntime = RuntimeState
        server_path = Path(__file__).resolve().parents[1] / "api" / "server.py"
        spec = importlib.util.spec_from_file_location("api_health_test_server", server_path)
        assert spec is not None and spec.loader is not None
        server = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"runtime.xrlf_runtime": runtime_module}):
            spec.loader.exec_module(server)
        self.runtime = RuntimeState()
        self.client = TestClient(server.create_app(self.runtime))
        self.addCleanup(self.client.close)

    def test_health_reports_loaded_model(self) -> None:
        self.runtime.loaded = True
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "ok",
            "model": "test-model",
            "runtime": "xrlf-1.0",
            "loaded": True,
            "loading": False,
            "load_state": "ready",
            "load_error": None,
        })

    def test_health_reports_load_state(self) -> None:
        self.runtime.loaded = False
        self.runtime.load_state = "loading"
        self.runtime.load_error = None
        h = self.client.get("/health").json()
        self.assertIs(h["loaded"], False)
        self.assertIs(h["loading"], True)
        self.assertEqual(h["load_state"], "loading")

    def test_health_reports_unloaded_model(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json().get("loaded"), False)

    def test_health_tracks_runtime_state_changes(self) -> None:
        for loaded in (False, True, False):
            with self.subTest(loaded=loaded):
                self.runtime.loaded = loaded
                health = self.client.get("/health").json()
                context = self.client.get("/v1/context").json()
                self.assertIs(health.get("loaded"), loaded)
                self.assertIs(health["loaded"], context["loaded"])


if __name__ == "__main__":
    unittest.main()
