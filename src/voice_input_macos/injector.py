"""Inject text into the currently focused window on macOS.

Primary method: clipboard + Cmd+V via pynput (requires Accessibility permission).
Fallback: AppleScript Cmd+V (slower, no Accessibility needed for paste itself).
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time

import pyperclip

log = logging.getLogger(__name__)


class InjectError(RuntimeError):
    pass


def paste_text(
    text: str,
    *,
    method: str = "paste",
    restore_clipboard: bool = True,
    paste_delay: float = 0.08,
) -> None:
    """Place `text` into clipboard and send Cmd+V to the focused window."""
    if not text:
        return

    if method == "applescript":
        _applescript_paste(text, restore_clipboard=restore_clipboard,
                           paste_delay=paste_delay)
        return

    # Default: pynput-based paste
    _pynput_paste(text, restore_clipboard=restore_clipboard,
                  paste_delay=paste_delay)


def _pynput_paste(
    text: str,
    *,
    restore_clipboard: bool,
    paste_delay: float,
) -> None:
    from pynput.keyboard import Controller, Key

    _keyboard = Controller()

    old: str | None = None
    if restore_clipboard:
        try:
            old = pyperclip.paste()
        except Exception:
            log.debug("could not read original clipboard; restore disabled")
            old = None

    try:
        pyperclip.copy(text)
    except Exception as e:
        raise InjectError(f"clipboard write failed: {e}") from e

    time.sleep(paste_delay)

    try:
        # Ensure no sticky modifier
        _keyboard.release(Key.cmd)
        with _keyboard.pressed(Key.cmd):
            _keyboard.press('v')
            _keyboard.release('v')
    except Exception as e:
        raise InjectError(f"Cmd+V send failed: {e}") from e

    if restore_clipboard and old is not None:
        def _restore():
            time.sleep(0.5)
            try:
                pyperclip.copy(old)
            except Exception:
                log.debug("clipboard restore failed (non-fatal)")

        threading.Thread(target=_restore, daemon=True).start()


def _applescript_paste(
    text: str,
    *,
    restore_clipboard: bool,
    paste_delay: float,
) -> None:
    """Fallback: use AppleScript for Cmd+V (no pynput/Accessibility needed)."""
    old: str | None = None
    if restore_clipboard:
        try:
            old = pyperclip.paste()
        except Exception:
            old = None

    try:
        pyperclip.copy(text)
    except Exception as e:
        raise InjectError(f"clipboard write failed: {e}") from e

    time.sleep(paste_delay)

    try:
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to keystroke "v" using command down'],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except Exception as e:
        raise InjectError(f"AppleScript paste failed: {e}") from e

    if restore_clipboard and old is not None:
        def _restore():
            time.sleep(0.5)
            try:
                pyperclip.copy(old)
            except Exception:
                pass

        threading.Thread(target=_restore, daemon=True).start()
