"""Inject text into the currently focused window on macOS.

Both paths require the running process (or its parent terminal) to be
granted Accessibility permission:

  - "paste":       pynput posts CGEvents directly.
  - "applescript": `osascript` drives System Events, which itself
                    needs Accessibility (+ Automation on newer macOS)
                    to synthesise keystrokes into other apps.

There is no truly permission-free way to paste on modern macOS.
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

    # Release any modifier the user may still be holding from the PTT
    # chord (option / shift / ctrl / cmd, both sides). Otherwise Cmd+V
    # becomes Cmd+Shift+V etc. and the target app sees the wrong combo.
    for mod in (Key.shift, Key.shift_r, Key.alt, Key.alt_r,
                Key.ctrl, Key.ctrl_r, Key.cmd, Key.cmd_r):
        try:
            _keyboard.release(mod)
        except Exception:
            pass

    try:
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
