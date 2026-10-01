import json
import os
import subprocess
import sys
import time
import urllib.request

CWD = os.path.dirname(os.path.abspath(__file__))
PORT = 8000
OUT = os.path.join(CWD, "boot_test_result.txt")


def main():
    lines = []
    # Kill port
    try:
        out = subprocess.check_output("netstat -ano -p tcp", shell=True).decode(
            errors="ignore"
        )
        for line in out.splitlines():
            if f":{PORT}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1].strip()
                    if pid.isdigit():
                        subprocess.run(
                            f"taskkill /F /PID {pid}", shell=True, capture_output=True
                        )
    except Exception:
        pass
    time.sleep(0.5)

    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=CWD,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    t0 = time.monotonic()
    status = None
    body = ""
    for _ in range(10):
        time.sleep(0.5)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/health")
            with urllib.request.urlopen(req, timeout=3) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
        except Exception as e:
            status = None
            body = str(e)
        if status == 200:
            break

    elapsed = time.monotonic() - t0
    lines.append(f"BOOT_TIME={elapsed:.3f}")
    lines.append(f"STATUS={status}")
    lines.append(f"BODY={body}")

    ok = False
    if status == 200:
        try:
            payload = json.loads(body)
            xv = payload.get("xrlf_version", "")
            lines.append(f"XRLF_VERSION={xv}")
            if xv == "3.0":
                lines.append("HEALTH=PASS")
                ok = True
            else:
                lines.append("HEALTH=FAIL_VERSION")
        except Exception as e:
            lines.append(f"HEALTH=FAIL_JSON={e}")
    else:
        lines.append("HEALTH=FAIL_NO_200")
        # Get stderr
        try:
            proc.terminate()
            _, stderr = proc.communicate(timeout=3)
            lines.append(f"STDERR={stderr.decode(errors='ignore')[:800]}")
        except Exception:
            pass

    if elapsed < 2.0:
        lines.append("BOOT_SPEED=PASS")
    else:
        lines.append("BOOT_SPEED=WARN")

    # Shutdown
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    result = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(result)


if __name__ == "__main__":
    main()
