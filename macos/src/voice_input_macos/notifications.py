"""macOS Notification Center integration via osascript."""
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)


def notify(title: str, message: str) -> None:
    """Show a macOS notification. Best-effort, failures are silent."""
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            capture_output=True,
            timeout=2,
        )
    except Exception:
        log.debug("notification failed (non-fatal)")
