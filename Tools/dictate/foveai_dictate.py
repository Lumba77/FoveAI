#!/usr/bin/env python3
"""FoveAI dictation — Win+H style speech-to-type for the desktop.

Super+H, AltGr+H, Shift+AltGr or F7 toggles dictation: a mic tray icon
spawns (grey while listening, red while speech is detected), audio streams
to the FoveAI STT websocket (:8409), and each finished utterance is typed
into the focused window via clipboard paste. Press the hotkey again to stop.

Bind with a Cinnamon custom keybinding, e.g.:
    command: /home/lumba/FoveAI/.venv/bin/python Tools/dictate/foveai_dictate.py
    binding: <Super>h

Env knobs:
    FOVEAI_STT_WS                  websocket URL (default ws://127.0.0.1:8409/ws)
    FOVEAI_DICTATE_SOURCE          PulseAudio source name (default: auto-pick mic_fx_source, then AUSDOM, else system default)
    FOVEAI_DICTATE_IDLE_TIMEOUT    seconds of no speech before auto-stop (default 180, 0=never)
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time

STT_URL = os.getenv("FOVEAI_STT_WS", "ws://127.0.0.1:8409/ws")
MIC_SOURCE = os.getenv("FOVEAI_DICTATE_SOURCE")
IDLE_TIMEOUT = float(os.getenv("FOVEAI_DICTATE_IDLE_TIMEOUT", "180"))
RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR", "/tmp")
PIDFILE = os.path.join(RUNTIME_DIR, "foveai-dictate.pid")
LOG = "/tmp/foveai-dictate.log"
CHUNK = 4096  # s16le 16kHz mono ≈ 128ms

SND_START = "/usr/share/sounds/freedesktop/stereo/bell.oga"
SND_STOP = "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga"


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass


def ding(path):
    if os.path.exists(path):
        subprocess.Popen(
            ["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )


def notify(title, body="", icon="audio-input-microphone"):
    try:
        subprocess.Popen(
            ["notify-send", "-a", "FoveAI", "-i", icon, "-t", "2500", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def pick_source():
    """Prefer the filtered mic (mic_fx_source), then AUSDOM, else system default."""
    if MIC_SOURCE:
        return MIC_SOURCE
    try:
        out = subprocess.check_output(
            ["pactl", "list", "short", "sources"], text=True, timeout=5
        )
        names = [
            l.split("\t")[1] if "\t" in l else l.split()[1]
            for l in out.splitlines()
            if l.strip()
        ]
        for name in names:
            if name == "mic_fx_source":
                return name
        for name in names:
            if "Sunplus" in name or "AUSDOM" in name:
                return name
    except Exception as e:
        log(f"pactl source scan failed: {e}")
    return None


# ---------------------------------------------------------------- icons


def make_icon(color):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=color)
    d.rounded_rectangle((25, 10, 39, 34), radius=7, fill="white")
    d.arc((18, 22, 46, 48), 20, 160, fill="white", width=4)
    d.line((32, 48, 32, 56), fill="white", width=4)
    d.line((24, 56, 40, 56), fill="white", width=4)
    return img


ICON_IDLE = "#666666"
ICON_REC = "#d32f2f"


class Indicator:
    """Borderless always-on-top circular mic badge, bottom-right of the
    work area (above the panel/calendar). Own X connection — safe to call
    from the asyncio thread while XTyper uses its own."""

    SIZE = 64
    MARGIN = 14

    def __init__(self):
        from Xlib import display

        self.d = display.Display()  # separate connection, thread-local use
        scr = self.d.screen()
        root = scr.root
        self.depth = scr.root_depth
        wx, wy = self._position(root, scr)
        self.win = root.create_window(
            wx,
            wy,
            self.SIZE,
            self.SIZE,
            0,
            self.depth,
            1,  # InputOutput
            scr.root_visual,
            override_redirect=True,
        )
        self._circle_mask(root)
        self.gc = self.win.create_gc()
        # 60% opaque — text under the badge stays readable through it
        try:
            from Xlib import Xatom

            opacity = int(0.60 * 0xFFFFFFFF)
            self.win.change_property(
                self.d.intern_atom("_NET_WM_WINDOW_OPACITY"),
                Xatom.CARDINAL,
                32,
                [opacity],
            )
        except Exception as e:
            log(f"opacity prop failed: {e}")
        self.win.map()
        self.d.sync()
        self.set_color(ICON_IDLE)

    def _work_area(self, root):
        wa = root.get_full_property(self.d.intern_atom("_NET_WORKAREA"), 0)
        if wa and len(wa.value) >= 4:
            return tuple(wa.value[:4])
        g = root.get_geometry()
        return (0, 0, g.width, g.height)

    def _position(self, root, scr):
        """FOVEAI_BADGE_POS=focus: badge sits beside the focused widget;
        default (corner): fixed at the panel's bottom-right corner."""
        sw, sh = scr.width_in_pixels, scr.height_in_pixels
        if os.getenv("FOVEAI_BADGE_POS", "corner") == "focus":
            try:
                fw = self.d.get_input_focus().focus
                g = fw.get_geometry()
                c = root.translate_coords(fw, 0, 0)  # widget origin in root coords
                rx, ry = c.x, c.y
                if g.width >= sw * 0.9 or g.height >= sh * 0.9:
                    # (near-)maximized window: pin inside its bottom-right,
                    # lifted above the app's own status/input strip
                    x = rx + g.width - self.SIZE - 16
                    y = ry + g.height - self.SIZE - 60
                elif 0 < g.width and 0 < g.height:
                    # normal window: just right of it, bottom-aligned
                    x = rx + g.width + 8
                    if x + self.SIZE > sw:
                        x = rx + g.width - self.SIZE - 8
                    y = ry + g.height - self.SIZE
                    if y < 0:
                        y = ry + 4
                else:
                    raise ValueError("degenerate focus window")
                return (max(0, min(x, sw - self.SIZE)), max(0, min(y, sh - self.SIZE)))
            except Exception as e:
                log(f"focus pos failed: {e}")
        x, y, w, h = self._work_area(root)
        return (x + w - self.SIZE - self.MARGIN, y + h - self.SIZE - self.MARGIN)

    def _circle_mask(self, root):
        try:
            from Xlib.ext import shape

            self.d.query_extension(shape.extname)  # binds shape_* methods
            pm = root.create_pixmap(self.SIZE, self.SIZE, 1)
            g0 = pm.create_gc(foreground=0)
            pm.fill_rectangle(g0, 0, 0, self.SIZE, self.SIZE)
            g1 = pm.create_gc(foreground=1)
            pm.fill_arc(g1, 0, 0, self.SIZE, self.SIZE, 0, 360 * 64)
            self.win.shape_mask(shape.SO.Set, shape.SK.Bounding, 0, 0, pm)
            pm.free()
        except Exception as e:
            log(f"shape mask failed (square badge): {e}")

    def set_color(self, color):
        from Xlib import X

        try:
            img = make_icon(color).convert("RGBA")
            px = img.tobytes()
            buf = bytearray(self.SIZE * self.SIZE * 4)
            for i in range(0, len(px), 4):
                # RGBA -> BGRX (little-endian 24-bit ZPixmap)
                buf[i] = px[i + 2]
                buf[i + 1] = px[i + 1]
                buf[i + 2] = px[i]
                buf[i + 3] = 255
            self.win.put_image(
                self.gc,
                0,
                0,
                self.SIZE,
                self.SIZE,
                X.ZPixmap,
                self.depth,
                0,
                bytes(buf),
            )
            self.d.sync()
        except Exception as e:
            log(f"indicator draw failed: {e}")

    def close(self):
        try:
            self.win.destroy()
            self.d.flush()
        except Exception:
            pass


# ---------------------------------------------------------------- typing


class XTyper:
    """Types text into the focused window via CLIPBOARD + Ctrl+V (XTEST)."""

    TERMINAL_HINTS = (
        "terminal",
        "xterm",
        "konsole",
        "alacritty",
        "kitty",
        "wezterm",
        "tilda",
        "guake",
        "terminator",
        "urxvt",
    )

    def __init__(self):
        from Xlib import display

        self.d = display.Display()
        self.clipboard = self.d.intern_atom("CLIPBOARD")
        self.utf8 = self.d.intern_atom("UTF8_STRING")
        self.targets = self.d.intern_atom("TARGETS")

    def _is_terminal(self):
        win = self.d.get_input_focus().focus
        for _ in range(10):
            if not win:
                return False
            cls = win.get_wm_class()
            if cls:
                return any(h in c.lower() for c in cls for h in self.TERMINAL_HINTS)
            parent = win.query_tree().parent
            if parent == win:
                return False
            win = parent
        return False

    def type_text(self, text):
        from Xlib import XK, X, Xatom
        from Xlib.ext import xtest
        from Xlib.protocol import event as xevent

        data = text.encode("utf-8")
        root = self.d.screen().root
        win = root.create_window(0, 0, 1, 1, 0, self.d.screen().root_depth)
        win.set_selection_owner(self.clipboard, X.CurrentTime)
        self.d.sync()
        if self.d.get_selection_owner(self.clipboard) != win:
            log("clipboard ownership failed")
            win.destroy()
            self.d.flush()
            return

        terminal = self._is_terminal()
        got_request = threading.Event()

        def serve(deadline):
            while time.time() < deadline:
                if not self.d.pending_events():
                    time.sleep(0.01)
                    continue
                ev = self.d.next_event()
                if ev.type != X.SelectionRequest:
                    continue
                prop = ev.property
                if ev.target == self.targets:
                    ev.requestor.change_property(
                        prop, Xatom.ATOM, 32, [self.targets, self.utf8, Xatom.STRING]
                    )
                elif ev.target in (self.utf8, Xatom.STRING):
                    ev.requestor.change_property(prop, ev.target, 8, list(data))
                else:
                    prop = X.NONE
                ev.requestor.send_event(
                    xevent.SelectionNotify(
                        requestor=ev.requestor,
                        selection=ev.selection,
                        target=ev.target,
                        property=prop,
                        time=ev.time,
                    )
                )
                self.d.flush()
                got_request.set()

        server = threading.Thread(target=serve, args=(time.time() + 4.0,), daemon=True)
        server.start()

        ctrl = self.d.keysym_to_keycode(XK.XK_Control_L)
        shift = self.d.keysym_to_keycode(XK.XK_Shift_L)
        v = self.d.keysym_to_keycode(XK.XK_v)
        xtest.fake_input(self.d, X.KeyPress, ctrl)
        if terminal:
            xtest.fake_input(self.d, X.KeyPress, shift)
        xtest.fake_input(self.d, X.KeyPress, v)
        xtest.fake_input(self.d, X.KeyRelease, v)
        if terminal:
            xtest.fake_input(self.d, X.KeyRelease, shift)
        xtest.fake_input(self.d, X.KeyRelease, ctrl)
        self.d.sync()

        got_request.wait(1.5)
        if not got_request.is_set():
            log("paste: no SelectionRequest — focus window may not accept paste")
        time.sleep(0.3)
        win.destroy()
        self.d.flush()


# ---------------------------------------------------------------- session


class DictationSession:
    def __init__(self):
        self.stop = threading.Event()
        self.icon = None
        self.indicator = None
        self.typer = None
        self.last_speech = time.time()

    def set_icon(self, color, tip):
        try:
            if self.icon:
                self.icon.icon = make_icon(color)
                self.icon.title = tip
        except Exception as e:
            log(f"icon update failed: {e}")
        try:
            if self.indicator:
                self.indicator.set_color(color)
        except Exception as e:
            log(f"indicator update failed: {e}")

    def _run_icon(self):
        import pystray

        self.icon = pystray.Icon(
            "foveai-dictate", make_icon(ICON_IDLE), "FoveAI dictation - connecting..."
        )
        self.icon.run()

    async def run(self):
        import websockets

        icon_thread = threading.Thread(target=self._run_icon, daemon=True)
        icon_thread.start()
        await asyncio.sleep(1.0)  # let the tray icon appear

        try:
            self.typer = XTyper()
        except Exception as e:
            log(f"XTyper init failed: {e}")
        try:
            self.indicator = Indicator()
        except Exception as e:
            log(f"Indicator init failed: {e}")

        try:
            async with websockets.connect(STT_URL, max_size=2**20) as ws:
                ready = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if ready.get("type") != "ready":
                    raise RuntimeError(f"unexpected handshake: {ready}")
                ding(SND_START)
                notify(
                    "FoveAI dictation ON", "Speak now - text types where your cursor is"
                )
                self.set_icon(ICON_IDLE, "FoveAI dictation - listening")

                src = pick_source()
                cmd = [
                    "parec",
                    "--format=s16le",
                    "--rate=16000",
                    "--channels=1",
                    "--latency-msec=60",
                ]
                if src:
                    cmd += ["--device", src]
                parec = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=subprocess.DEVNULL
                )
                log(f"parec started (source={src or 'default'})")

                pump = asyncio.create_task(self._pump(ws, parec))
                try:
                    await self._events(ws)
                finally:
                    pump.cancel()
                    if parec.returncode is None:
                        parec.terminate()
                    # Flush the server-side buffer so the tail of the last
                    # utterance still transcribes before we close.
                    try:
                        await ws.send(json.dumps({"type": "stop"}))
                        await asyncio.wait_for(
                            self._events(ws, drain=True), timeout=4.0
                        )
                    except Exception:
                        pass
        except Exception as e:
            log(f"session error: {e}")
        finally:
            ding(SND_STOP)
            notify("FoveAI dictation OFF", "", "microphone-sensitivity-muted")
            if self.indicator:
                self.indicator.close()
            if self.icon:
                try:
                    self.icon.stop()
                except Exception:
                    pass

    async def _pump(self, ws, parec):
        while not self.stop.is_set():
            data = await parec.stdout.read(CHUNK)
            if not data:
                break
            await ws.send(data)

    async def _events(self, ws, drain=False):
        while drain or not self.stop.is_set():
            if IDLE_TIMEOUT and (time.time() - self.last_speech) > IDLE_TIMEOUT:
                log("idle timeout — auto-stop")
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
            try:
                msg = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            kind = msg.get("type")
            if kind == "speech_start":
                self.last_speech = time.time()
                self.set_icon(ICON_REC, "FoveAI dictation - recording")
            elif kind == "speech_end":
                self.set_icon(ICON_IDLE, "FoveAI dictation - listening")
            elif kind == "final":
                self.last_speech = time.time()
                text = (msg.get("text") or "").strip()
                if text and self.typer:
                    log(f"type: {text[:80]}")
                    await asyncio.to_thread(self.typer.type_text, text + " ")
            elif kind == "ack" and msg.get("status") == "stopped":
                break


def session_main():
    sess = DictationSession()

    def on_signal(*_):
        log("stop requested")
        sess.stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    try:
        asyncio.run(sess.run())
    finally:
        try:
            os.remove(PIDFILE)
        except OSError:
            pass


# ---------------------------------------------------------------- toggle


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- hotkey


def _connect_display():
    from Xlib import display as xdisplay

    seen = []
    for name in [os.getenv("DISPLAY", ":0"), ":0", ":20", ":1"]:
        if name in seen:
            continue
        seen.append(name)
        try:
            d = xdisplay.Display(name)
            d.sync()
            return d
        except Exception:
            continue
    raise RuntimeError(f"no reachable X display (tried {seen})")


def listen_main():
    """X-level hotkey grabber — works without cinnamon-settings-daemon.

    Grabs Super+H and Shift+AltGr (either modifier order). Grabbed keys are
    swallowed by the grab, so no letter leaks into the focused window.
    """
    from Xlib import XK, X
    from Xlib import error as xerror

    d = _connect_display()
    root = d.screen().root
    # Modifier map is authoritative: which keycodes generate each modifier
    mm = d.get_modifier_mapping()  # (Shift, Lock, Control, Mod1..Mod5)
    shifts = [k for k in mm[0] if k]
    altgrs = [k for k in mm[7] if k]  # Mod5 = AltGr
    h = d.keysym_to_keycode(XK.XK_h)
    # NumLock/CapsLock variants so the combo still fires with them on
    locks = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]

    f7 = d.keysym_to_keycode(XK.XK_F7)
    grabs = []
    for m in locks:
        grabs.append((h, X.Mod4Mask | m, "Super+H"))
        grabs.append((h, X.Mod5Mask | m, "AltGr+H"))
        grabs.append((f7, m, "F7"))
        for ag in altgrs:
            grabs.append((ag, X.ShiftMask | m, "Shift+AltGr"))
        for sk in shifts:
            grabs.append((sk, X.Mod5Mask | m, "AltGr+Shift"))
    for key, mods, label in grabs:
        try:
            root.grab_key(key, mods, False, X.GrabModeAsync, X.GrabModeAsync)
            d.sync()
        except xerror.BadAccess:
            log(f"grab failed ({label}): key={key} mods={mods}")

    last = 0.0
    log("hotkey listener ready")
    while True:
        ev = d.next_event()
        if ev.type != X.KeyPress:
            continue
        now = time.time()
        if now - last < 0.8:  # debounce autorepeat
            continue
        last = now
        log("hotkey fired")
        toggle()


def toggle():
    pid = None
    try:
        with open(PIDFILE) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        pass

    if pid and pid_alive(pid):
        log(f"toggle: stopping pid {pid}")
        os.kill(pid, signal.SIGTERM)
        return

    log("toggle: starting session")
    logf = open(LOG, "a")
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--session"],
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


if __name__ == "__main__":
    if "--session" in sys.argv:
        session_main()
    elif "--listen" in sys.argv:
        listen_main()
    else:
        toggle()
