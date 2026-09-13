"""audioRecorder.py — cross-platform mic recorder for Jenna.

Protocol (stdin lines):
    start <outfile.wav>   — begin recording to file
    stop                  — finish and finalize the wav
    cancel                — stop without keeping the file
    quit                  — exit

Stdout signals: ready / started / saved <path> / error <msg>

Windows uses winmm MCI. Linux tries pw-record, parecord, arecord, ffmpeg
(first available wins).
"""

import os
import platform
import shutil
import signal
import subprocess
import sys

IS_WIN = platform.system() == 'Windows'

_winmm = None
_proc = None          # linux recorder subprocess
_current_path = None  # pending output file


def _linux_cmd(path):
    """Pick the first available Linux recorder and return its argv."""
    if shutil.which('pw-record'):
        return ['pw-record', '--rate', '16000', '--channels', '1', '--format', 's16', path]
    if shutil.which('parecord'):
        return ['parecord', '--rate=16000', '--channels=1', '--format=s16le',
                '--file-format=wav', path]
    if shutil.which('arecord'):
        return ['arecord', '-q', '-f', 'S16_LE', '-r', '16000', '-c', '1', path]
    if shutil.which('ffmpeg'):
        return ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'pulse', '-i', 'default',
                '-ac', '1', '-ar', '16000', path]
    return None


def _start(path):
    global _proc, _current_path
    _current_path = path
    if IS_WIN:
        _winmm.mciSendStringA(b'record jenna_mic', None, 0, 0)
    else:
        argv = _linux_cmd(path)
        if not argv:
            print('error no recorder backend found (pw-record/parecord/arecord/ffmpeg)', flush=True)
            return
        _proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('started', flush=True)


def _stop(save):
    global _proc, _current_path
    path = _current_path
    if IS_WIN:
        if save and path:
            _winmm.mciSendStringA(b'save jenna_mic ' + os.path.abspath(path).encode(), None, 0, 0)
            _winmm.mciSendStringA(b'close jenna_mic', None, 0, 0)
            _winmm.mciSendStringA(b'open new type waveaudio alias jenna_mic', None, 0, 0)
    else:
        if _proc:
            try:
                _proc.send_signal(signal.SIGINT)  # lets the tool finalize wav headers
                _proc.wait(timeout=4)
            except Exception:
                try:
                    _proc.kill()
                except Exception:
                    pass
            _proc = None
        if not save and path:
            try:
                os.unlink(path)
            except OSError:
                pass
    _current_path = None
    print('saved ' + (path or ''), flush=True)


if IS_WIN:
    import ctypes
    _winmm = ctypes.windll.winmm
    _winmm.mciSendStringA(b'open new type waveaudio alias jenna_mic', None, 0, 0)

print('ready', flush=True)

for line in sys.stdin:
    parts = line.strip().split(' ', 1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else None
    if cmd == 'start':
        _start(arg or 'jenna_recording.wav')
    elif cmd == 'stop':
        _stop(save=True)
    elif cmd == 'cancel':
        _stop(save=False)
    elif cmd == 'quit':
        _stop(save=False)
        break
