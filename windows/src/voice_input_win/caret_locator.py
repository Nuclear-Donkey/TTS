"""Locate where to place the floating window relative to the text caret.

Strategy (Windows only):
    1. GetForegroundWindow() → thread id → GetGUIThreadInfo(.hwndCaret, .rcCaret)
       If rcCaret is non-empty, map client coords → screen coords and return
       the caret's bottom-left point.
    2. Fallback: GetCursorPos() — mouse position.
    3. Fallback: top-center of primary screen.

The caret approach works for native Win32 edit controls, classic Notepad,
and some Office fields. It silently fails for Chrome/VSCode/Electron/
terminals because they render their own caret. We accept the fallback
instead of trying to UIA-probe every app (slow, fragile).
"""
from __future__ import annotations

import logging
import sys
from typing import Tuple

log = logging.getLogger(__name__)


def _caret_screen_pos() -> Tuple[int, int] | None:
    """Returns screen (x, y) just below-left of the text caret, or None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND),
                ("rcCaret", RECT),
            ]

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        if not tid:
            return None

        gti = GUITHREADINFO()
        gti.cbSize = ctypes.sizeof(GUITHREADINFO)
        if not user32.GetGUIThreadInfo(tid, ctypes.byref(gti)):
            return None
        if not gti.hwndCaret:
            return None
        r = gti.rcCaret
        if r.right == r.left and r.bottom == r.top:
            return None

        # Map caret's bottom-left from client → screen coords
        pt = wintypes.POINT(r.left, r.bottom)
        if not user32.ClientToScreen(gti.hwndCaret, ctypes.byref(pt)):
            return None
        return int(pt.x), int(pt.y)
    except Exception:
        log.debug("caret lookup failed", exc_info=True)
        return None


def _mouse_screen_pos() -> Tuple[int, int] | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    except Exception:
        log.debug("cursor pos lookup failed", exc_info=True)
    return None


def locate(panel_width: int, panel_height: int) -> Tuple[int, int]:
    """Best-effort screen (x, y) for the panel's top-left corner.

    The panel is placed just below-and-right of the input caret (if any),
    or below-right of the mouse cursor. Result is clamped to the primary
    screen so the panel doesn't clip off-screen.
    """
    anchor = _caret_screen_pos() or _mouse_screen_pos()
    # Compute a sensible offset from the anchor
    if anchor is not None:
        x, y = anchor
        # Place below the caret with a small gap; nudge right so it doesn't
        # cover the caret itself.
        px = x - 8
        py = y + 18
    else:
        # Top-center of primary screen
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return (100, 100)
        geo = screen.availableGeometry()
        px = geo.x() + (geo.width() - panel_width) // 2
        py = geo.y() + 80

    # Clamp to primary screen geometry
    try:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            px = max(geo.x() + 8, min(px, geo.x() + geo.width() - panel_width - 8))
            py = max(geo.y() + 8, min(py, geo.y() + geo.height() - panel_height - 8))
    except Exception:
        pass
    return int(px), int(py)
