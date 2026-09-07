"""Dry-run boot test for the XRLF 3.0 Spatial Machine engine.

Starts the server, waits for /health, validates the payload, then shuts down.
Writes results to dry_run_result.txt.
"""
import os
import sys
import time
import json
import subprocess
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dry_run_result.txt")
PORT = 8402


def write_result(text):
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


def check_health():
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/health",
            headers={"User-Agent": "DryRun/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except Exception as e:
        return None, str(e)


def main():
    write_result("DRY_RUN_START\n")

    # Kill anything on port 8402 first
    try:
        netstat = subprocess.check_output("netstat -ano -p tcp", shell=True).decode(errors="ignore")
        for line in netstat.splitlines():
            if f":{PORT}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1].strip()
                    if pid.isdigit():
                        subprocess.run(["taskkill", "/F", "/PID", pid], shell=True, capture_output=True)
    except Exception:
        pass

    time.sleep(0.5)

    # Start the server
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    boot_start = time.monotonic()

    # Wait for health endpoint (max 5 seconds)
    status = None
    body = ""
    for _ in range(10):
        time.sleep(0.5)
        elapsed = time.monotonic() - boot_start
        status, body = check_health()
        if status == 200:
            break

    elapsed = time.monotonic() - boot_start

    result_lines = [f"DRY_RUN_START\n"]
    result_lines.append(f"Boot elapsed: {elapsed:.3f}s\n")
    result_lines.append(f"Health status: {status}\n")
    result_lines.append(f"Health body: {body}\n")

    if status == 200:
        try:
            payload = json.loads(body)
            xrlf_ver = payload.get("xrlf_version", "")
            result_lines.append(f"xrlf_version: {xrlf_ver}\n")
            if xrlf_ver == "3.0":
                result_lines.append("HEALTH_CHECK: PASS (xrlf_version=3.0)\n")
            else:
                result_lines.append(f"HEALTH_CHECK: FAIL (xrlf_version={xrlf_ver}, expected 3.0)\n")
        except Exception as e:
            result_lines.append(f"HEALTH_CHECK: FAIL (json parse error: {e})\n")

        if elapsed < 2.0:
            result_lines.append(f"BOOT_TIME: PASS ({elapsed:.3f}s < 2.0s)\n")
        else:
            result_lines.append(f"BOOT_TIME: WARN ({elapsed:.3f}s >= 2.0s)\n")
    else:
        result_lines.append("HEALTH_CHECK: FAIL (no 200 response)\n")
        # Capture stderr
        try:
            proc.terminate()
            _, stderr = proc.communicate(timeout=3)
            result_lines.append(f"Server stderr: {stderr.decode(errors='ignore')[:500]}\n")
        except Exception:
            pass

    result_lines.append("DRY_RUN_END\n")

    # Shutdown server
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    write_result("".join(result_lines))


if __name__ == "__main__":
    main()