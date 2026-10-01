import ctypes
import sys

winmm = ctypes.windll.winmm
winmm.mciSendStringA(b"open new type waveaudio alias jenna_mic", None, 0, 0)

print("ready", flush=True)

for line in sys.stdin:
    cmd = line.strip()
    if cmd == "start":
        winmm.mciSendStringA(b"record jenna_mic", None, 0, 0)
        print("started", flush=True)
    elif cmd.startswith("stop"):
        parts = cmd.split(" ", 1)
        if len(parts) > 1:
            filename = parts[1]
            winmm.mciSendStringA(b"save jenna_mic " + filename.encode(), None, 0, 0)
            print("saved", flush=True)
            # Reset the alias for the next recording
            winmm.mciSendStringA(b"close jenna_mic", None, 0, 0)
            winmm.mciSendStringA(b"open new type waveaudio alias jenna_mic", None, 0, 0)
    elif cmd == "quit":
        winmm.mciSendStringA(b"close jenna_mic", None, 0, 0)
        break
