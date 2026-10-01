#!/usr/bin/env python3
"""
Start the creative service with environment variables loaded from .env file.
This ensures FoveAI_INVOKEAI_MODELS_ROOT and FoveAI_INVOKEAI_MODELS_CSV are set.
"""

import os
import subprocess
import sys
from pathlib import Path


def load_env_file(env_path):
    """Load environment variables from a .env file."""
    if not os.path.isfile(env_path):
        print(f"Warning: .env file not found at {env_path}")
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes
                if len(value) >= 2 and (
                    (value[0] == '"' and value[-1] == '"')
                    or (value[0] == "'" and value[-1] == "'")
                ):
                    value = value[1:-1]
                if key and value:
                    os.environ[key] = value
                    print(f"Set {key}={value[:50]}{'...' if len(value) > 50 else ''}")


def main():
    # Get the directory of this script
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    # Load .env from repo root
    env_path = repo_root / ".env"
    print(f"Loading environment from {env_path}")
    load_env_file(str(env_path))

    # Print key InvokeAI variables for debugging
    print("\n--- InvokeAI Integration ---")
    print(
        f"FoveAI_INVOKEAI_MODELS_ROOT: {os.environ.get('FoveAI_INVOKEAI_MODELS_ROOT', '(not set)')}"
    )
    print(
        f"FoveAI_INVOKEAI_MODELS_CSV: {os.environ.get('FoveAI_INVOKEAI_MODELS_CSV', '(not set)')}"
    )
    print(
        f"FoveAI_INVOKEAI_MERGE_CONTROLNETS: {os.environ.get('FoveAI_INVOKEAI_MERGE_CONTROLNETS', '(not set)')}"
    )
    print()

    # Start the creative service
    creative_service = script_dir / "creative_service.py"
    if not creative_service.exists():
        print(f"Error: creative_service.py not found at {creative_service}")
        sys.exit(1)

    print(f"Starting creative_service.py from {script_dir}")

    # Run the creative service - use Popen to not block
    proc = subprocess.Popen(
        [sys.executable, str(creative_service)],
        cwd=str(script_dir),
        env=os.environ.copy(),
    )

    print(f"Creative service started with PID {proc.pid}")
    print("The service is now running on http://localhost:8003")

    # Wait for the process
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("Creative service stopped")


if __name__ == "__main__":
    main()
