"""Inject text into the currently focused window.

v0.1 only supports the "paste" method (clipboard + simulated Ctrl+V),
which works across Claude Code CLI / PowerShell / Terminal / Edge /
Chrome / VSCode / Electron apps / Office. The alternative (typing each
character via SendInput) is brittle for CJK and disabled here.

The clipboard is restored after a short delay so the user's clipboard
history isn't silently clobbered — best effort (if the target app
pastes the old content instead of the new, that's the expected bug).
"""
from __future__ import annotations

import logging
import threading
import time

import pyperclip
import keyboard

log = logging.getLogger(__name__)


class InjectError(RuntimeError):
    pass


def paste_text(
    text: str,
    *,
    restore_clipboard: bool = True,
    paste_delay: float = 0.05,
) -> None:
    """Place `text` into the clipboard and send Ctrl+V to the focused window.

    If `restore_clipboard`, fetch the old clipboard first and restore it
    asynchronously ~0.5s after the paste so the target app has time to
    consume our value. Restore failures are logged and ignored.
    """
    if not text:
        return

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
        keyboard.send("ctrl+v")
    except Exception as e:
        raise InjectError(f"ctrl+v send failed: {e}") from e

    if restore_clipboard and old is not None:
        def _restore():
            time.sleep(0.5)
            try:
                pyperclip.copy(old)
            except Exception:
                log.debug("clipboard restore failed (non-fatal)")

        threading.Thread(target=_restore, daemon=True).start()
