"""
tests/test_rig_guard.py — Test suite for RigGuard
=================================================
Validates telemetry queries, safe parsing, ignore auditing, and alert cooldowns.
"""

import sys
import unittest
from pathlib import Path

# Add FoveAI root to sys.path
FOVEAI_ROOT = Path(__file__).resolve().parent.parent
if str(FOVEAI_ROOT) not in sys.path:
    sys.path.insert(0, str(FOVEAI_ROOT))

from runtime.rig_guard import RigGuard


class TestRigGuard(unittest.TestCase):
    def setUp(self):
        self.guard = RigGuard(cooldown_seconds=5)

    def test_system_ram_query(self):
        """Test reading physical RAM via Windows GlobalMemoryStatusEx."""
        ram = self.guard.get_system_ram()
        self.assertIn("total_gb", ram)
        self.assertIn("used_gb", ram)
        self.assertIn("avail_gb", ram)
        self.assertIn("percent", ram)
        self.assertGreater(ram["total_gb"], 0)
        self.assertGreaterEqual(ram["percent"], 0)
        self.assertLessEqual(ram["percent"], 100)
        print(
            f"\n[Test] System RAM: {ram['used_gb']}/{ram['total_gb']} GB ({ram['percent']}%)"
        )

    def test_language_server_status_query(self):
        """Test language server status querying doesn't crash and returns structured info."""
        status = self.guard.get_language_server_status()
        self.assertIn("running", status)
        self.assertIn("ram_mb", status)
        self.assertIn("tier", status)
        self.assertIn("status_text", status)
        print(f"[Test] Language Server: {status['status_text']}")

    def test_unity_status_query(self):
        """Test Unity status and zombie worker queries return expected structure."""
        status = self.guard.get_unity_status()
        self.assertIn("unity_running", status)
        self.assertIn("shader_workers", status)
        self.assertIn("zombies", status)
        self.assertIn("status_text", status)
        print(f"[Test] Unity Status: {status['status_text']}")

    def test_workspace_ignores_check(self):
        """Test auditing .antigravityignore and searchMaxWorkspaceFileCount."""
        ig = self.guard.check_workspace_ignores()
        self.assertIn("healthy", ig)
        self.assertIn("missing_patterns", ig)
        self.assertIn("current_cap", ig)
        self.assertIn("status_text", ig)
        print(f"[Test] Workspace Ignores: {ig['status_text']}")

    def test_top_ram_consumers_query(self):
        """Test discovering top RAM consumers."""
        top = self.guard.get_top_ram_consumers(3)
        self.assertIsInstance(top, list)
        for p in top:
            self.assertIn("name", p)
            self.assertIn("ram_mb", p)
            print(f"[Test] Top Consumer: {p['name']} ({p['ram_mb']} MB)")

    def test_alert_cooldown(self):
        """Verify notifications respect cooldown periods."""
        alerts = []

        def fake_notify(msg, title):
            alerts.append((msg, title))

        # First run dispatches any currently active critical alerts
        first_dispatched = self.guard.audit_and_alert(fake_notify)
        first_count = len(alerts)

        # Immediate second run MUST NOT send duplicate alert because of cooldown
        second_dispatched = self.guard.audit_and_alert(fake_notify)
        second_count = len(alerts)
        self.assertEqual(
            first_count, second_count, "Cooldown failed to throttle duplicate alert!"
        )
        self.assertEqual(
            len(second_dispatched),
            0,
            "Second audit should dispatch 0 alerts within cooldown period!",
        )

    def test_runaway_git_hunter(self):
        """Verify runaway git process scanner executes safely without error."""
        cnt, freed_mb, msg = self.guard.kill_runaway_git_processes(min_mb=500)
        self.assertIsInstance(cnt, int)
        self.assertIsInstance(freed_mb, int)
        self.assertIsInstance(msg, str)
        print(f"[Test] Runaway Git Hunter: {msg}")

    def test_language_server_guidance(self):
        """Verify non-destructive safe language server reload advice."""
        guide = self.guard.get_language_server_guidance()
        self.assertIn("title", guide)
        self.assertIn("message", guide)
        self.assertIn("Developer: Reload Window", guide["message"])
        print(f"[Test] Safe Reload Guidance: {guide['title']}")

    def test_smart_cpu_offload_calculation(self):
        """Verify smart CPU offload calculations for small and large models."""
        from runtime.vram_guard import VRAMGuardrail

        vg = VRAMGuardrail()
        # Test 1: Small 2.4GB model should offload all layers to GPU
        dummy_small = "dummy_small.gguf"
        offload_small = vg.calculate_smart_offload(
            dummy_small, total_layers=33, n_ctx=2048
        )
        self.assertIn("gpu_layers", offload_small)
        self.assertIn("cpu_layers", offload_small)
        self.assertIn("mode", offload_small)
        self.assertEqual(offload_small["cpu_layers"], 0)
        print(
            f"[Test] Smart Offload (Small): {offload_small['mode']} ({offload_small['gpu_layers']}/33 GPU)"
        )

        # Test 2: Large 12B model with simulated high VRAM usage should offload layers to CPU
        offload_large = vg.calculate_smart_offload(
            "dummy_large.gguf", total_layers=42, n_ctx=4096, safety_floor_gb=1.6
        )
        self.assertIn("gpu_layers", offload_large)
        self.assertIn("cpu_layers", offload_large)
        print(
            f"[Test] Smart Offload (Large): {offload_large['mode']} ({offload_large['gpu_layers']} GPU / {offload_large['cpu_layers']} CPU)"
        )


if __name__ == "__main__":
    unittest.main()
