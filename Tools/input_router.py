#!/usr/bin/env python3
"""input_router.py — route physical keyboard/mouse into an X display via XTEST.

Reads evdev devices directly (needs rw on /dev/input/event*), grabs them, and
replays events into DISPLAY via XTEST, where they land on whatever window has
focus.  Built for headless/Xvfb sessions (CRD :20, gamescope) where the X
server has no evdev input path of its own.

Toggle:  ScrollLock switches between ROUTE (grab physical devices, inject into
         X) and PASS-THROUGH (release grabs, console/greeter gets them back).
         The ScrollLock LED mirrors the state.

Env:     INPUT_ROUTER_DISPLAY   target X display      (default :20)
         INPUT_ROUTER_AUTO      1=route at start       (default 1)
         INPUT_ROUTER_DEVICES   comma list of eventN to include (default: auto)
"""

import ctypes
import ctypes.util
import fcntl
import glob
import os
import select
import signal
import struct
import sys
import time

# ---------------------------------------------------------------- evdev ----

EVENT_FMT = "llHHI"  # input_event on 64-bit: timeval + type + code + value
EVENT_SZ = struct.calcsize(EVENT_FMT)

EV_SYN, EV_KEY, EV_REL, EV_MSC, EV_LED = 0x00, 0x01, 0x02, 0x04, 0x11
KEY_A, KEY_Z, KEY_ENTER, KEY_SCROLLLOCK = 30, 44, 28, 70
REL_X, REL_Y, REL_WHEEL, REL_HWHEEL = 0, 1, 8, 6
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0x110, 0x111, 0x112
BTN_SIDE, BTN_EXTRA = 0x113, 0x114
LED_SCROLLL = 0

_IOC_READ, _IOC_WRITE = 2, 1


def _ioc(d, t, nr, size):
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr


def EVIOCGBIT(ev, ln):
    return _ioc(_IOC_READ, "E", 0x20 + ev, ln)


def EVIOCGNAME(ln):
    return _ioc(_IOC_READ, "E", 0x06, ln)


EVIOCGRAB = _ioc(_IOC_WRITE, "E", 0x90, 4)
EVIOCUNGRAB = _ioc(_IOC_WRITE, "E", 0x91, 4)


def _bits(fd, ev, ln=128):
    buf = ctypes.create_string_buffer(ln)
    fcntl.ioctl(fd, EVIOCGBIT(ev, ln), buf, True)
    return buf.raw


def _has_keycode(bits, code):
    return bits[code // 8] & (1 << (code % 8)) != 0


def dev_name(fd):
    buf = ctypes.create_string_buffer(256)
    try:
        fcntl.ioctl(fd, EVIOCGNAME(256), buf, True)
        return buf.value.decode("utf-8", "replace")
    except OSError:
        return "?"


def classify(fd):
    """'kbd' | 'ptr' | None  based on capability bits."""
    try:
        ev = _bits(fd, 0)
    except OSError:
        return None
    has_key, has_rel = _has_keycode(ev, EV_KEY), _has_keycode(ev, EV_REL)
    if has_key:
        kb = _bits(fd, EV_KEY)
        if all(_has_keycode(kb, c) for c in (KEY_A, KEY_Z, KEY_ENTER)):
            return "kbd"
        if _has_keycode(kb, BTN_LEFT) and has_rel:
            rel = _bits(fd, EV_REL)
            if _has_keycode(rel, REL_X) and _has_keycode(rel, REL_Y):
                return "ptr"
    return None


VIRTUAL_HINTS = ("uinput", "inputplumber", "virtual", "xtest")


def find_devices(allow=None):
    """{path: (fd, kind, name)} for physical kbd/pointer devices."""
    out = {}
    for path in sorted(glob.glob("/dev/input/event*")):
        n = int(path.rsplit("event", 1)[1])
        if allow and n not in allow:
            continue
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            continue
        name = dev_name(fd)
        if any(h in name.lower() for h in VIRTUAL_HINTS):
            os.close(fd)
            continue
        kind = classify(fd)
        if kind:
            out[path] = [fd, kind, name]
        else:
            os.close(fd)
    return out


# ------------------------------------------------------------------ X ------

x11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
xtst = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xtst") or "libXtst.so.6")

x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
x11.XFlush.argtypes = [ctypes.c_void_p]
x11.XStringToKeysym.restype = ctypes.c_ulong
x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
x11.XKeysymToKeycode.restype = ctypes.c_ubyte
x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
xtst.XTestFakeRelativeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]

XKB_OFFSET = 8  # evdev KEY_x -> X keycode for the standard AT range

# evdev code -> X keysym name, for keys outside the +8 AT range
SPECIAL_KEYS = {
    113: "XF86AudioMute", 114: "XF86AudioLowerVolume", 115: "XF86AudioRaiseVolume",
    142: "XF86Sleep", 143: "XF86WakeUp", 150: "XF86WWW", 152: "XF86ScreenSaver",
    155: "XF86Mail", 158: "XF86Back", 159: "XF86Forward", 161: "XF86Eject",
    163: "XF86AudioNext", 164: "XF86AudioPlay", 165: "XF86AudioPrev",
    166: "XF86AudioStop", 167: "XF86AudioRecord", 172: "XF86HomePage",
    173: "XF86Refresh", 180: "XF86HomePage", 181: "XF86New",
    217: "XF86Search", 140: "XF86Calculator", 148: "XF86Calculator",
    224: "XF86MonBrightnessDown", 225: "XF86MonBrightnessUp",
    227: "XF86AudioMedia", 234: "XF86AudioMedia",
    240: "XF86TouchpadToggle", 245: "XF86Display",
    171: "XF86Favorites", 156: "XF86Launch1", 157: "XF86Launch2",
}

X_BUTTONS = {BTN_LEFT: 1, BTN_MIDDLE: 2, BTN_RIGHT: 3, BTN_SIDE: 8, BTN_EXTRA: 9}
WHEEL_BTN = {REL_WHEEL: (4, 5), REL_HWHEEL: (6, 7)}  # (pos, neg)


class XTarget:
    def __init__(self, name):
        self.name = name
        self.dpy = None
        self._spare = None          # keycode pool for remapped keysyms
        self._remap = {}            # evdev code -> remapped X keycode

    def connect(self):
        while self.dpy is None:
            self.dpy = x11.XOpenDisplay(self.name.encode())
            if self.dpy is None:
                log(f"XOpenDisplay({self.name}) failed; retry in 5s")
                time.sleep(5)
        log(f"connected to X display {self.name}")

    def keycode(self, evcode):
        if evcode < 250:
            return evcode + XKB_OFFSET
        return 0

    def key(self, evcode, down):
        kc = self._remap.get(evcode)
        if kc is None:
            kc = self.keycode(evcode)
            if kc == 0 and evcode in SPECIAL_KEYS:
                kc = self._remap_keysym(evcode, SPECIAL_KEYS[evcode])
        if not kc:
            return
        xtst.XTestFakeKeyEvent(self.dpy, kc, 1 if down else 0, 0)

    def button(self, btn, down):
        xtst.XTestFakeButtonEvent(self.dpy, btn, 1 if down else 0, 0)

    def motion(self, dx, dy):
        xtst.XTestFakeRelativeMotionEvent(self.dpy, dx, dy, 0)

    def flush(self):
        x11.XFlush(self.dpy)

    # -- spare-keycode remap for keysyms missing from the server keymap --
    def _remap_keysym(self, evcode, symname):
        ks = x11.XStringToKeysym(symname.encode())
        if not ks:
            return 0
        kc = x11.XKeysymToKeycode(self.dpy, ks)
        if not kc:
            log(f"no keycode for {symname} (server keymap lacks it); skipping")
            kc = 0
        self._remap[evcode] = kc
        return kc


# ---------------------------------------------------------------- router ---

_running = True


def log(msg):
    print(f"[input-router] {msg}", flush=True)


def _sig(*_):
    global _running
    _running = False


def set_led(dev, on):
    fd, kind, _ = dev
    if kind != "kbd":
        return
    ev = struct.pack(EVENT_FMT, 0, 0, EV_LED, LED_SCROLLL, 1 if on else 0)
    try:
        os.write(fd, ev)
    except OSError:
        pass


def grab(dev, on):
    try:
        fcntl.ioctl(dev[0], EVIOCGRAB if on else EVIOCUNGRAB, 0)
    except OSError:
        pass


def main():
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    target_name = os.environ.get("INPUT_ROUTER_DISPLAY", ":20")
    allow = os.environ.get("INPUT_ROUTER_DEVICES")
    allow = {int(x) for x in allow.split(",")} if allow else None
    routing = os.environ.get("INPUT_ROUTER_AUTO", "1") != "0"

    xt = XTarget(target_name)
    devices = {}

    def rescan():
        for path, d in list(devices.items()):
            pass  # keep existing
        for path, d in find_devices(allow).items():
            if path not in devices:
                devices[path] = d
                log(f"+ {d[1]} {path} \"{d[2]}\"")
                if routing:
                    grab(d, True)
                    set_led(d, routing)

    rescan()
    if not devices:
        log("no input devices found — check /dev/input permissions")

    while _running:
        if not xt.dpy:
            xt.connect()
        try:
            r, _, _ = select.select([d[0] for d in devices.values()], [], [], 5)
        except OSError:
            r = []
        if not r:
            rescan()  # periodic pick-up of hotplugged devices
            continue

        dx = dy = 0
        flushed = False
        for fd in r:
            dev = next((d for d in devices.values() if d[0] == fd), None)
            if dev is None:
                continue
            try:
                data = os.read(fd, EVENT_SZ * 64)
            except OSError:
                log(f"device lost: {dev[2]} — rescanning")
                os.close(fd)
                devices.pop(next(p for p, d in devices.items() if d[0] == fd), None)
                rescan()
                continue
            for off in range(0, len(data) - EVENT_SZ + 1, EVENT_SZ):
                _, _, etype, ecode, eval_ = struct.unpack_from(EVENT_FMT, data, off)
                if etype == EV_SYN:
                    if dx or dy:
                        if routing:
                            xt.motion(dx, dy)
                        dx = dy = 0
                    if routing:
                        xt.flush()
                    flushed = True
                    continue
                if etype == EV_KEY:
                    if ecode == KEY_SCROLLLOCK and eval_ == 1:
                        routing = not routing
                        for d in devices.values():
                            grab(d, routing)
                            set_led(d, routing)
                        log("ROUTING " + ("ON → " + target_name if routing else "OFF (pass-through)"))
                        continue
                    if not routing:
                        continue
                    if ecode >= BTN_LEFT and ecode in X_BUTTONS:
                        xt.button(X_BUTTONS[ecode], eval_ != 0)
                    else:
                        # value: 0 up, 1 down, 2 autorepeat — forward as-is
                        xt.key(ecode, eval_ != 0)
                elif etype == EV_REL and routing:
                    if ecode == REL_X:
                        dx += eval_
                    elif ecode == REL_Y:
                        dy += eval_
                    elif ecode in WHEEL_BTN:
                        pos, neg = WHEEL_BTN[ecode]
                        for _ in range(abs(eval_)):
                            xt.button(pos if eval_ > 0 else neg, True)
                            xt.button(pos if eval_ > 0 else neg, False)
        if routing and not flushed:
            xt.flush()

    for d in devices.values():
        grab(d, False)
        set_led(d, False)
    log("exit — grabs released")


if __name__ == "__main__":
    sys.exit(main())
