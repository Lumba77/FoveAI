#!/usr/bin/env python3
"""
audio_player.py — Robust Windows Audio Playback for Virtual Desktop & Meta Quest

Handles dynamic Windows audio device switches, Virtual Desktop Audio,
and default MMDevice endpoints with automatic fallback.
"""

import os
import subprocess
import sys


def play_wav_file(wav_path: str) -> bool:
    """
    Play a WAV audio file on Windows, auto-scanning sounddevice for Virtual Desktop Audio,
    Oculus VAD, or active speaker/headphone outputs.
    """
    if not os.path.exists(wav_path):
        print(f"[AudioPlayer] File not found: {wav_path}")
        return False

    abs_path = os.path.abspath(wav_path)

    # 1. Try sounddevice with intelligent Virtual Desktop / Oculus / Active Speaker matching
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        data, samplerate = sf.read(abs_path)
        data_float = data.astype(np.float32)
        devices = sd.query_devices()

        target_device_idx = None
        # Preferred keywords for Virtual Desktop, Quest headsets, and 3.5mm audio jacks
        preferred_keywords = [
            "virtual desktop",
            "vdvad",
            "oculus",
            "rode",
            "realtek",
            "high definition",
            "speakers",
            "headphone",
            "line out",
        ]

        for pref in preferred_keywords:
            for idx, dev in enumerate(devices):
                if (
                    dev["max_output_channels"] > 0
                    and "wdm-ks" not in dev["name"].lower()
                ):
                    name_lower = dev["name"].lower()
                    if pref in name_lower:
                        target_device_idx = idx
                        print(
                            f"[AudioPlayer] Found targeted audio output device #{idx}: {dev['name']}"
                        )
                        break
            if target_device_idx is not None:
                break

        if target_device_idx is not None:
            sd.play(data_float, samplerate, device=target_device_idx)
            sd.wait()
            print(
                f"[AudioPlayer] ✅ Successfully played audio to device #{target_device_idx}"
            )
            return True
        else:
            # Play on default output
            sd.play(data_float, samplerate)
            sd.wait()
            print("[AudioPlayer] ✅ Played audio to default output")
            return True

    except Exception as e:
        print(f"[AudioPlayer] sounddevice playback failed: {e}")

    # 2. Fallback to Windows SoundPlayer
    try:
        ps_cmd = f"$p = New-Object Media.SoundPlayer '{abs_path}'; $p.PlaySync()"
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            print("[AudioPlayer] ✅ Played audio via Windows SoundPlayer fallback")
            return True
    except Exception as e:
        print(f"[AudioPlayer] SoundPlayer fallback failed: {e}")

    return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        play_wav_file(sys.argv[1])
    else:
        print("Usage: python audio_player.py <path_to_wav>")
