import argparse
import json
import os
import subprocess
import sys


def _safe_none(reason: str) -> str:
    return json.dumps({"actions": ["none"], "reason": reason}, ensure_ascii=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe wrapper for local coder/runner output.")
    parser.add_argument("--model", required=True, help="Model identifier for the local runner.")
    parser.add_argument("--prompt", required=True, help="Prompt text (already includes constraints).")
    args = parser.parse_args()

    runner_cmd = os.getenv("FoveAI_LOCAL_RUNNER_CMD", "runner").strip()
    runner_entry = os.getenv("FoveAI_LOCAL_RUNNER_ENTRY", "").strip()
    timeout = float(os.getenv("FoveAI_LOCAL_RUNNER_TIMEOUT_SEC", "20"))

    cmd = [runner_cmd]
    if runner_entry:
        cmd.append(runner_entry)
    cmd.extend(["--model", args.model, "--prompt", args.prompt])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        text = (proc.stdout or "").strip()
        if text:
            sys.stdout.write(text)
            return 0
        err = (proc.stderr or "").strip()
        sys.stdout.write(_safe_none(f"runner-empty:{err[:180]}"))
        return 0
    except Exception as e:
        sys.stdout.write(_safe_none(f"runner-error:{e}"))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

