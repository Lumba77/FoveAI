#!/usr/bin/env python3
"""foveai-bouncer — demand-wake supervisor for the FoveAI fleet.

Warm-freezes fleet units (SIGSTOP) once their ports are listening, thaws a
unit on the first inbound TCP connection to any of its ports, and re-freezes
it after a quiet window. Push-driven services with no inbound listener are
exempted. State machine per unit: loading -> warm -> frozen <-> live.

Pure stdlib + /proc + systemctl; runs as root from foveai-wake.service.

Env: BOUNCER_INTERVAL=0.5  BOUNCER_IDLE=120  BOUNCER_WARM_WAIT=4
     BOUNCER_LOG=/home/lumba/foveai_bouncer.log
"""
import os
import re
import subprocess
import time

CHECK_INTERVAL = float(os.getenv("BOUNCER_INTERVAL", "0.5"))
IDLE_SECONDS = float(os.getenv("BOUNCER_IDLE", "120"))
WARM_WAIT = float(os.getenv("BOUNCER_WARM_WAIT", "4.0"))
LOG_PATH = os.getenv("BOUNCER_LOG", "/home/lumba/foveai_bouncer.log")

EXEMPT_UNITS = {
    "foveai-wake.service", "foveai-sudo-broker.service",
    "foveai-nerve.service", "foveai-jen-snapshot.service",
    "foveai-harden.service", "foveai-harden.timer",
    "foveai-gamepad.service", "foveai-quest-apk.service",
    "foveai-mind.service",
    "foveai-llama-2b-proxy.service", "foveai-llama-9b-proxy.service",
    "foveai-creative-proxy.service",
}
# socket doors: relay -> engine. If the engine dies while the relay lives,
# the door jams (socket only triggers an inactive service) — doorkeeper stops
# the relay so the next knock re-triggers the whole chain fresh.
DOORS = {
    "foveai-llama-2b-proxy.service": "foveai-llama-2b-wake.service",
    "foveai-llama-9b-proxy.service": "foveai-llama-9b.service",
    "foveai-creative-proxy.service": "foveai-creative.service",
}
DOOR_REARM = 180.0
# door port -> short name; every fresh inbound row on a door port is recorded
# in GUEST_LOG (who knocked, from where, when).
DOOR_PORTS = {8407: "2b", 8613: "9b", 8412: "creative"}
GUEST_LOG = "/home/lumba/guest.log"
DIAG = bool(os.getenv("BOUNCER_DIAG"))
UNIT_RE = re.compile(r"(foveai-\S+?\.service)$")

log_fh = open(LOG_PATH, "a", buffering=1)
t0 = time.time()
def log(*a):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime(time.time()-t0))}]", *a, file=log_fh)

def set_state(t, u, new, why):
    if t.state != new:
        log(u, t.state, "->", new, f"({why})")
        t.state = new

def sh(*args):
    return subprocess.run(args, capture_output=True, text=True).returncode == 0

def signal_unit(unit, sig, why):
    if sh("systemctl", "kill", f"--signal={sig}", unit):
        log(unit, "->", sig, f"({why})")
        return True
    log(unit, "signal FAILED", sig, f"({why})")
    return False

def listen_table():
    """port -> inode for LISTEN sockets (tcp4 + tcp6)."""
    tab = {}
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as f:
                for row in list(f)[1:]:
                    c = row.split()
                    if len(c) < 10 or c[3] != "0A":
                        continue
                    port = int(c[1].split(":")[1], 16)
                    tab.setdefault(port, c[9])
        except (OSError, ValueError):
            continue
    return tab

def ino_unit():
    """inode -> unit name; from socket fds of pids in system.slice."""
    m = {}
    ino2unit = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cgroup") as f:
                cg = f.read()
        except OSError:
            continue
        unit = None
        for line in cg.splitlines():
            seg = line.rsplit("/", 1)[-1]
            mm = UNIT_RE.search(seg)
            if "/system.slice/" in line and mm:
                unit = mm.group(1)
        if not unit or unit in EXEMPT_UNITS:
            continue
        ino2unit[pid] = unit
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                try:
                    tgt = os.readlink(f"/proc/{pid}/fd/{fd}")
                except OSError:
                    continue
                if tgt.startswith("socket:["):
                    m[tgt[8:-1]] = unit
        except OSError:
            pass
    return m

def unit_ports():
    umap = {}
    tab, inou = listen_table(), ino_unit()
    for port, inode in tab.items():
        unit = inou.get(inode)
        if unit:
            umap.setdefault(unit, []).append(port)
    return umap

# units whose model load outlasts their early port bind (llama/uvicorn bind
# before weights finish loading): longer grace before warm-freeze and idle
# refreeze, else SIGSTOP stalls the load mid-flight.
SLOW_UNITS = {
    "foveai-llama-2b-wake.service", "foveai-llama-9b.service",
    "foveai-creative.service",
}
SLOW_FACTOR = 60.0  # slow units: grace * SLOW_FACTOR (4s -> 240s, 120s * 2 via idle floor)

def warm_wait(u):
    return WARM_WAIT * SLOW_FACTOR if u in SLOW_UNITS else WARM_WAIT

def idle_for(u):
    return max(IDLE_SECONDS, WARM_WAIT * SLOW_FACTOR) if u in SLOW_UNITS else IDLE_SECONDS

def ip_dotted(hx):
    a = [int(hx[i:i+2], 16) for i in (6, 4, 2, 0)]
    return ".".join(str(x) for x in a)

def guest_knock(lport, row):
    try:
        raddr, rport = row[2].split(":")
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')}"
                f"  guest {ip_dotted(raddr)}:{int(rport, 16)}"
                f" -> door :{lport} ({DOOR_PORTS[lport]})\n")
        with open(GUEST_LOG, "a") as g:
            g.write(line)
    except OSError:
        pass

def tcp_rows():
    rows = []
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as f:
                for row in list(f)[1:]:
                    rows.append(row.split())
        except OSError:
            continue
    return rows

def door_rearm():
    """Close jammed doors: relay up + engine cold for > DOOR_REARM s.

    The socket door only triggers its relay when the relay is INACTIVE. If a
    triggered engine later dies (crash, stop, oomd) the relay keeps running
    and every fresh connection dies against a cold upstream. Stopping the
    relay re-arms the door; the next knock starts the whole chain fresh.
    """
    for proxy, engine in DOORS.items():
        if not sh("systemctl", "is-active", "--quiet", proxy):
            continue
        if sh("systemctl", "is-active", "--quiet", engine):
            continue
        out = subprocess.run(
            ["systemctl", "show", proxy,
             "--property=ActiveEnterTimestampMonotonic", "--value"],
            capture_output=True, text=True)
        try:
            start_ns = int(out.stdout.strip())
        except ValueError:
            continue
        if time.monotonic_ns() - start_ns >= DOOR_REARM * 1e9:
            log(proxy, "door jammed (engine cold) — closing to re-arm")
            sh("systemctl", "stop", proxy)

class Tracked:
    __slots__ = ("ports", "state", "warm_t", "last_seen")
    def __init__(self):
        self.ports, self.state, self.warm_t, self.last_seen = [], "loading", 0.0, 0.0

def main():
    units = {}        # unit -> Tracked
    seen_keys = set() # (port, raddr) ESTAB keys observed before (wake on NEW only)
    prev_bytes = {}   # unit -> total queue bytes last tick
    baseline = False  # first scan seeds seen_keys silently — no wake storm at boot
    door_t = 0.0      # last doorkeeper sweep
    while True:
        for unit, ports in unit_ports().items():
            units.setdefault(unit, Tracked()).ports = ports
        now = time.time()

        new_key, bytes_now, had_conn = {}, {}, {}
        for row in tcp_rows():
            if row[3] not in ("01", "02", "03"):
                continue
            lport = int(row[1].split(":")[1], 16)
            if baseline and lport in DOOR_PORTS and (lport, row[2]) not in seen_keys:
                seen_keys.add((lport, row[2]))
                guest_knock(lport, row)
            for u, t in units.items():
                if lport in t.ports:
                    b = sum(int(x, 16) for x in row[4].split(":")[:2])
                    bytes_now[u] = bytes_now.get(u, 0) + b
                    had_conn[u] = True
                    key = (lport, row[2])
                    if key not in seen_keys:
                        if baseline:
                            new_key[u] = True
                        seen_keys.add(key)
        baseline = True

        for u, t in units.items():
            if not t.ports:
                continue  # no listener yet (or engine cold/downed) — leave alone
            if t.state in ("loading", "warm", "frozen"):
                if new_key.get(u) or (t.state == "frozen" and bytes_now.get(u, 0) > prev_bytes.get(u, 0)):
                    signal_unit(u, "SIGCONT", "demand: inbound connection")
                    set_state(t, u, "live", "demand: inbound connection")
                    t.last_seen = now
                elif t.state == "loading":
                    set_state(t, u, "warm", "port is listening")
                    t.warm_t = now
                elif t.state == "warm":
                    if bytes_now.get(u, 0) > prev_bytes.get(u, 0):
                        t.warm_t = now  # traffic flowing; keep waiting
                    elif now - t.warm_t >= warm_wait(u) and bytes_now.get(u, 0) == 0:
                        signal_unit(u, "SIGSTOP", "warm-freeze after listen")
                        set_state(t, u, "frozen", "warm-freeze after listen")
            elif t.state == "live":
                if new_key.get(u) or (bytes_now.get(u, 0) > prev_bytes.get(u, 0)):
                    t.last_seen = now
                elif now - t.last_seen >= idle_for(u) * 3:
                    signal_unit(u, "SIGSTOP", f"idle {idle_for(u) * 3:.0f}s (open sockets ignored)")
                    set_state(t, u, "frozen", f"idle {idle_for(u) * 3:.0f}s")
                elif now - t.last_seen >= idle_for(u) and not had_conn.get(u):
                    signal_unit(u, "SIGSTOP", f"idle {idle_for(u):.0f}s")
                    set_state(t, u, "frozen", f"idle {idle_for(u):.0f}s")
        prev_bytes.update(bytes_now)
        if now - door_t >= 45:
            door_t = now
            door_rearm()
        if len(seen_keys) > 8192:
            seen_keys.clear()
        if DIAG:
            diag_t1 = int(now)
            if not hasattr(main, "_diag") or diag_t1 > main._diag:
                main._diag = diag_t1
                log("TICK", {u: t.state for u, t in units.items()})
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()