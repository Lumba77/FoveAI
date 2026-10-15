"""
Unit test for AutonomousPipelineRunner state machine and lifecycle.
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Forge.nursery.autonomous_pipeline import (
    AutonomousPipelineRunner,
    PipelineConfig,
    STAGE_QUEUED,
    STAGE_COMPLETED,
)


def test_pipeline_lifecycle():
    temp_dir = tempfile.mkdtemp(prefix="pipeline_test_")
    try:
        runner = AutonomousPipelineRunner(runs_dir=temp_dir)
        cfg = PipelineConfig(
            variant_id="test-companion-v1",
            name="Test Companion",
            description="Testing autonomous pipeline lifecycle",
            base_model="Qwen3.5-9B",
            datasets=["test_dataset"],
            quant_type="moq-3.0",
            epochs=1,
            batch_size=1,
            auto_register=False,
            validate_model=False,
        )

        state = runner.create_run(cfg)
        assert state.run_id.startswith("run-")
        assert state.stage == STAGE_QUEUED
        assert os.path.exists(os.path.join(temp_dir, f"{state.run_id}.json"))

        runner.log(state, "Test message logged successfully")
        assert len(state.logs) >= 1
        assert os.path.exists(os.path.join(temp_dir, f"{state.run_id}.log"))

        # Test reload from disk
        runner2 = AutonomousPipelineRunner(runs_dir=temp_dir)
        assert state.run_id in runner2.runs
        loaded = runner2.runs[state.run_id]
        assert loaded.config.variant_id == "test-companion-v1"
        print("✓ Pipeline state persistence and logging OK")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_pipeline_lifecycle()
