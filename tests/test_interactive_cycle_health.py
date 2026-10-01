"""
tests/test_interactive_cycle_health.py — Health endpoint tests for biological cycle services.

Verifies that all 7 biological-cycle FastAPI apps expose /health endpoints
returning the expected JSON shape with status="ok".
"""

import importlib.util
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi.testclient import TestClient


class TestInteractiveCycleHealth(unittest.TestCase):
    """Tests that all sensory services expose /health endpoints."""

    def setUp(self) -> None:
        # Load interactive_cycle.py with a mocked .env
        cycle_path: Path = (
            Path(__file__).resolve().parents[1] / "Backend" / "interactive_cycle.py"
        )
        spec = importlib.util.spec_from_file_location("interactive_cycle", cycle_path)
        assert spec is not None and spec.loader is not None
        module: ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module

        # Create test clients for each service app
        self.clients: dict[str, TestClient] = {
            "sight": TestClient(module.app_sight),
            "hearing": TestClient(module.app_hearing),
            "contemplation": TestClient(module.app_contemplation),
            "speech": TestClient(module.app_speech),
            "body": TestClient(module.app_body),
            "subconscious_in": TestClient(module.app_sub_in),
            "subconscious_out": TestClient(module.app_sub_out),
        }
        for c in self.clients.values():
            self.addCleanup(c.close)

    def test_sight_health(self) -> None:
        r = self.clients["sight"].get("/health")
        self.assertEqual(r.status_code, 200)
        body: dict[str, Any] = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "sight")

    def test_hearing_health(self) -> None:
        r = self.clients["hearing"].get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "hearing")

    def test_contemplation_health(self) -> None:
        r = self.clients["contemplation"].get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "contemplation")
        self.assertIn("loaded", body)

    def test_speech_health(self) -> None:
        r = self.clients["speech"].get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "speech")

    def test_body_health(self) -> None:
        r = self.clients["body"].get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "body")

    def test_subconscious_in_health(self) -> None:
        r = self.clients["subconscious_in"].get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "subconscious_in")

    def test_subconscious_out_health(self) -> None:
        r = self.clients["subconscious_out"].get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "subconscious_out")

    def test_all_health_endpoints_return_ok(self) -> None:
        """All 7 services must return status=ok from /health."""
        for name, client in self.clients.items():
            with self.subTest(service=name):
                r = client.get("/health")
                self.assertEqual(
                    r.status_code, 200, f"{name} /health returned {r.status_code}"
                )
                self.assertEqual(
                    r.json()["status"], "ok", f"{name} did not return status=ok"
                )

    def test_contemplation_root_endpoint(self) -> None:
        """The contemplation service root should return identity info."""
        r = self.clients["contemplation"].get("/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "online")
        self.assertEqual(body["role"], "Frontal Lobe")

    def test_all_services_have_port_in_health(self) -> None:
        """Every health response should include the port number."""
        for name, client in self.clients.items():
            with self.subTest(service=name):
                r = client.get("/health")
                self.assertIn("port", r.json(), f"{name} health missing 'port' field")
                self.assertIsInstance(r.json()["port"], int)


if __name__ == "__main__":
    unittest.main()
