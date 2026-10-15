#!/usr/bin/env python3
"""
spotify_ctl.py — Spotify MPRIS controller & status probe for FoveAI Console & Nest.

Controls local Spotify client via DBus MPRIS2 interface:
- Status / Metadata (track, artist, album, status, position, length)
- Playback control (play, pause, play_pause, next, prev, volume)
- Client lifecycle (launch)
"""

import json
import os
import subprocess
import sys

try:
    import dbus
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False

SPOTIFY_BUS = "org.mpris.MediaPlayer2.spotify"
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


def get_spotify_player():
    if not HAS_DBUS:
        return None
    try:
        bus = dbus.SessionBus()
        obj = bus.get_object(SPOTIFY_BUS, MPRIS_PATH)
        player = dbus.Interface(obj, PLAYER_IFACE)
        props = dbus.Interface(obj, PROPS_IFACE)
        return player, props
    except Exception:
        return None


def is_running() -> bool:
    if HAS_DBUS:
        try:
            bus = dbus.SessionBus()
            names = bus.get_object(
                "org.freedesktop.DBus", "/org/freedesktop/DBus"
            ).ListNames(dbus_interface="org.freedesktop.DBus")
            return SPOTIFY_BUS in names
        except Exception:
            pass
    res = subprocess.run(["pgrep", "-x", "spotify"], capture_output=True)
    return res.returncode == 0


def get_status() -> dict:
    if not is_running():
        return {"running": False, "status": "offline"}

    player_data = get_spotify_player()
    if not player_data:
        return {"running": True, "status": "idle"}

    _, props = player_data
    try:
        playback_status = str(props.Get(PLAYER_IFACE, "PlaybackStatus"))
        meta = props.Get(PLAYER_IFACE, "Metadata")
        title = str(meta.get("xesam:title", ""))
        artists = [str(a) for a in meta.get("xesam:artist", [])]
        artist = ", ".join(artists) if artists else ""
        album = str(meta.get("xesam:album", ""))
        length_us = int(meta.get("mpris:length", 0))
        length_s = length_us // 1000000

        all_props = props.GetAll(PLAYER_IFACE)
        volume = float(all_props.get("Volume", 1.0))
        pos_us = int(all_props.get("Position", 0))
        pos_s = pos_us // 1000000

        return {
            "running": True,
            "status": playback_status,
            "title": title,
            "artist": artist,
            "album": album,
            "position": pos_s,
            "length": length_s,
            "volume": round(volume, 2),
        }
    except Exception as e:
        return {"running": True, "status": "active", "error": str(e)}


def play_pause() -> bool:
    p = get_spotify_player()
    if p:
        try:
            p[0].PlayPause()
            return True
        except Exception:
            pass
    # Fallback to dbus-send
    res = subprocess.run(
        [
            "dbus-send",
            "--session",
            "--dest=" + SPOTIFY_BUS,
            "--type=method_call",
            MPRIS_PATH,
            PLAYER_IFACE + ".PlayPause",
        ],
        capture_output=True,
    )
    return res.returncode == 0


def next_track() -> bool:
    p = get_spotify_player()
    if p:
        try:
            p[0].Next()
            return True
        except Exception:
            pass
    res = subprocess.run(
        [
            "dbus-send",
            "--session",
            "--dest=" + SPOTIFY_BUS,
            "--type=method_call",
            MPRIS_PATH,
            PLAYER_IFACE + ".Next",
        ],
        capture_output=True,
    )
    return res.returncode == 0


def prev_track() -> bool:
    p = get_spotify_player()
    if p:
        try:
            p[0].Previous()
            return True
        except Exception:
            pass
    res = subprocess.run(
        [
            "dbus-send",
            "--session",
            "--dest=" + SPOTIFY_BUS,
            "--type=method_call",
            MPRIS_PATH,
            PLAYER_IFACE + ".Previous",
        ],
        capture_output=True,
    )
    return res.returncode == 0


def launch() -> bool:
    if not is_running():
        try:
            env = os.environ.copy()
            if "DISPLAY" not in env:
                env["DISPLAY"] = ":0"
            if "XAUTHORITY" not in env:
                env["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")
            subprocess.Popen(
                ["spotify"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except Exception:
            return False
    return True


def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    if cmd in ("status", "info"):
        print(json.dumps(get_status()))
    elif cmd in ("play-pause", "toggle", "playpause"):
        success = play_pause()
        print(json.dumps({"success": success}))
    elif cmd in ("next", "skip"):
        success = next_track()
        print(json.dumps({"success": success}))
    elif cmd in ("prev", "previous"):
        success = prev_track()
        print(json.dumps({"success": success}))
    elif cmd in ("launch", "start"):
        success = launch()
        print(json.dumps({"success": success}))
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
