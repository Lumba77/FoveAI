"""
Windows application desktop toolbar (AppBar) — reserve a screen edge band so
maximized windows respect that strip (SHAppBarMessage). Windows only.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from tkinter import TclError

if sys.platform != "win32":
    raise RuntimeError("appbar_win32 is Windows-only")

shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32

ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOSIZE = 0x00000002
ABM_SETPOS = 0x00000003

ABE_TOP = 1
ABE_BOTTOM = 3

WM_USER = 0x0400


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", RECT),
        ("lParam", wintypes.LPARAM),
    ]


def _hwnd_from_tk(w) -> int:
    w.update_idletasks()
    return int(w.winfo_id())


def register_appbar(
    hwnd: int, edge: int = ABE_BOTTOM, callback_msg: int = WM_USER + 88
) -> bool:
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    abd.uCallbackMessage = callback_msg
    abd.uEdge = edge
    return bool(shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd)))


def remove_appbar(hwnd: int) -> None:
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))


def query_set_top_band(hwnd: int, height_px: int) -> tuple[int, int, int, int]:
    """
    After ABM_NEW, query/set top edge.
    """
    cx = user32.GetSystemMetrics(0)
    cy = user32.GetSystemMetrics(1)

    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    abd.uEdge = ABE_TOP
    abd.rc.left = 0
    abd.rc.top = 0
    abd.rc.right = cx
    abd.rc.bottom = height_px

    shell32.SHAppBarMessage(ABM_QUERYPOSIZE, ctypes.byref(abd))
    shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))

    return int(abd.rc.left), int(abd.rc.top), int(abd.rc.right), int(abd.rc.bottom)


def apply_top_appbar_band(w, height_px: int = 32) -> tuple[int, int, int, int]:
    """
    Register as top appbar and return (x, y, width, height) for geometry().
    """
    hwnd = _hwnd_from_tk(w)
    if not register_appbar(hwnd, edge=ABE_TOP):
        raise RuntimeError("SHAppBarMessage ABM_NEW failed")
    left, top, right, bottom = query_set_top_band(hwnd, height_px)
    return left, top, max(1, right - left), max(1, bottom - top)


def query_set_bottom_band(hwnd: int) -> tuple[int, int, int, int]:
    """
    After ABM_NEW, query/set bottom edge. Uses full-screen probe rect per MSDN;
    Shell returns the usable band (often above the taskbar when sharing the bottom edge).
    """
    cx = user32.GetSystemMetrics(0)
    cy = user32.GetSystemMetrics(1)

    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    abd.uEdge = ABE_BOTTOM
    abd.rc.left = 0
    abd.rc.top = 0
    abd.rc.right = cx
    abd.rc.bottom = cy

    shell32.SHAppBarMessage(ABM_QUERYPOSIZE, ctypes.byref(abd))
    shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))

    return int(abd.rc.left), int(abd.rc.top), int(abd.rc.right), int(abd.rc.bottom)


def apply_bottom_appbar_band(w) -> tuple[int, int, int, int]:
    """
    Register as bottom appbar and return (x, y, width, height) for geometry().
    Call when the Tk window is mapped.
    """
    hwnd = _hwnd_from_tk(w)
    if not register_appbar(hwnd):
        raise RuntimeError("SHAppBarMessage ABM_NEW failed")
    left, top, right, bottom = query_set_bottom_band(hwnd)
    return left, top, max(1, right - left), max(1, bottom - top)


def cleanup_appbar(w) -> None:
    try:
        hwnd = _hwnd_from_tk(w)
        remove_appbar(hwnd)
    except (TclError, RuntimeError, OSError, ValueError, ctypes.ArgumentError):
        pass
