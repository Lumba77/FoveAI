#!/usr/bin/env python3
"""
pc_micro_wheels.py — read-only host auditor: what is actually slowing this PC down.

Rewritten 2026-10-17. The earlier draft "pre-warmed" the 10 .xrlb beds (69 KB in
total) into /dev/shm and created empty RAM dirs — that changes nothing measurable,
so it was removed. This version only MEASURES, and points at the root script
(Tools/pc_speedup_root.sh) for the changes that need sudo.

Measured facts that shaped it (2026-10-16/17):
  * /, /home/lumba and /agent live on sda2 (5400 rpm HDD) after the account
    migration from the SSD (sdb2); sda sat at ~100 % util with only ~3 MB/s read,
    i.e. it is seek-bound, not bandwidth-bound.
  * foveai-jen-snapshot.service (git add -A over /agent/jen) ran > 1 h per pass.
  * 11.9 GB of swap in use on the HDD while ~11 GB RAM was reclaimable cache.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def _read(p: str) -> str:
    try:
        return Path(p).read_text()
    except OSError:
        return ""


def _sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def disk_util(dev: str = "sda", seconds: float = 2.0) -> float | None:
    def io_ms() -> int | None:
        for line in _read("/proc/diskstats").splitlines():
            f = line.split()
            if len(f) > 12 and f[2] == dev:
                return int(f[12])
        return None

    a = io_ms()
    time.sleep(seconds)
    b = io_ms()
    if a is None or b is None:
        return None
    return round((b - a) / (seconds * 10), 1)  # % of wall time the disk was busy


def base_disk(source: str) -> str:
    name = os.path.basename(source)
    return name.rstrip("0123456789") if name.startswith("sd") else name


def rotational(dev: str) -> bool | None:
    v = _read(f"/sys/block/{dev}/queue/rotational").strip()
    return None if not v else v == "1"


def swap_report() -> list[dict]:
    out = []
    for line in _read("/proc/swaps").splitlines()[1:]:
        f = line.split()
        if len(f) >= 5:
            src = _sh(["df", "--output=source", f[0]]).splitlines()[-1] if f[0].startswith("/") else ""
            dev = base_disk(src)
            out.append({"file": f[0], "size_mb": int(f[2]) // 1024, "used_mb": int(f[3]) // 1024,
                        "on_device": dev, "rotational": rotational(dev)})
    return out


def swap_hogs(min_mb: int = 200) -> list[dict]:
    hogs = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        for line in _read(f"{d}/status").splitlines():
            if line.startswith("VmSwap:"):
                mb = int(line.split()[1]) // 1024
                if mb >= min_mb:
                    cmd = _read(f"{d}/cmdline").replace("\0", " ").strip()[:100]
                    hogs.append({"pid": int(d.name), "swap_mb": mb, "cmd": cmd})
    return sorted(hogs, key=lambda h: -h["swap_mb"])


def d_state() -> list[dict]:
    rows = []
    for line in _sh(["ps", "-eo", "stat,etime,user,cmd"]).splitlines()[1:]:
        if line.startswith("D"):
            rows.append({"line": line[:130]})
    return rows


def snapshot_job() -> dict:
    s = _sh(["systemctl", "show", "foveai-jen-snapshot.service", "-p", "ActiveState,ExecMainStartTimestamp"])
    return dict(x.split("=", 1) for x in s.splitlines() if "=" in x)


def main() -> None:
    home_src = _sh(["df", "--output=source", str(Path.home())]).splitlines()[-1]
    home_dev = base_disk(home_src)
    report = {
        "home_on": {"device": home_dev, "rotational": rotational(home_dev)},
        "sda_util_pct": disk_util("sda"),
        "swappiness": _read("/proc/sys/vm/swappiness").strip(),
        "swap": swap_report(),
        "swap_hogs": swap_hogs(),
        "snapshot_job": snapshot_job(),
        "d_state_processes": d_state(),
        "next_step": "sudo bash Tools/pc_speedup_root.sh --diagnose   (then --apply)",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
