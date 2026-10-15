#!/usr/bin/env python3
"""Guard-gated llama-server launcher for the FoveAI systemd units.

The units used to hardcode `--n-gpu-layers` (40/999) and bypass the VRAM
guard entirely. This launcher replaces that ExecStart: it consults
`runtime.vram_guard` for

  1. the gaming gate  — refuse to start a model into a GPU a game owns, and
  2. a live smart CPU/GPU layer split — never over-commit VRAM and crash the box,

then `execv`s llama-server in place (so the PID systemd tracks is the server
itself, and shutdown/journald behave exactly as before). On refusal it exits
non-zero so systemd records the reason in the journal.

Set FOVEAI_ALLOW_GAMING_OVERLOAD=1 in a unit's Environment to bypass the gate.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from runtime.vram_guard import guardrail  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Guard-gated llama-server launcher")
    ap.add_argument("--llama", required=True, help="absolute path to llama-server")
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument(
        "--requested-layers", type=int, default=0,
        help="desired GPU layers; <=0 means 'all, if they fit'",
    )
    ap.add_argument("--mmproj")
    ap.add_argument("--draft")
    ap.add_argument("--spec-draft-n-max", type=int, default=40)
    ap.add_argument("--cache-type")
    ap.add_argument("--flash-attn", action="store_true")
    ap.add_argument("--jinja", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--dry-run", action="store_true", help="print the resolved command and exit")
    ap.add_argument("extra", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    model = a.model
    if not Path(model).exists():
        print(f"[llama_launch] model not found: {model}", file=sys.stderr)
        return 1

    # 1) Gaming gate: never start a model into a GPU a game already owns.
    gaming = guardrail.gaming_gate()
    if gaming is not None:
        print(
            "[llama_launch] \U0001f3ae refusing to load "
            f"{Path(model).name}: " + "; ".join(gaming["reasons"]),
            file=sys.stderr,
        )
        return 1

    # 2) Smart layer split from live VRAM. Clamp to the model's real depth,
    #    never a sentinel: `-ngl 999` corrupts the KV-cache estimate.
    total = guardrail.model_layer_count(model) or max(a.requested_layers, 1)
    offload = guardrail.calculate_smart_offload(
        model, total_layers=total, n_ctx=a.ctx
    )
    if offload["gpu_layers"] >= total:
        layers = min(a.requested_layers, total) if a.requested_layers > 0 else total
    else:
        layers = offload["gpu_layers"]

    cmd = [
        a.llama, "-m", model,
        "--port", str(a.port), "--host", a.host,
        "--ctx-size", str(a.ctx), "--n-gpu-layers", str(layers),
    ]
    if a.mmproj:
        cmd += ["--mmproj", a.mmproj]
    if a.draft:
        cmd += [
            "-md", a.draft,
            "--spec-draft-n-max", str(a.spec_draft_n_max),
            "--gpu-layers-draft", "99",
        ]
    if a.cache_type:
        cmd += ["--cache-type-k", a.cache_type, "--cache-type-v", a.cache_type]
    if a.flash_attn:
        cmd += ["--flash-attn", "on"]
    if a.jinja:
        cmd += ["--jinja"]
    cmd += a.extra

    print(
        f"[llama_launch] {offload['mode']}: n_gpu_layers={layers}/{total} "
        f"(free={offload['real_free_vram_gb']}GB, need={offload['total_needed_gb']}GB) "
        f"\u2014 exec llama-server on :{a.port}"
    )
    sys.stdout.flush()
    if a.dry_run:
        print("[llama_launch] DRY-RUN:", " ".join(cmd))
        return 0
    os.execv(cmd[0], cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
