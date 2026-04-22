"""macos Accessibility permission helpers."""
from __future__ import annotations

import logging

import HIServices

log = logging.getLogger(__name__)


def check_accessibility() -> bool:
    """Check whether this process has Accessibility permission."""
    return HIServices.AXIsProcessTrusted()


def prompt_accessibility() -> None:
    """Trigger the macOS Accessibility permission dialog."""
    try:
        HIServices.AXIsProcessTrustedWithOptions(
            {HIServices.kAXTrustedCheckOptionPrompt: True}
        )
    except Exception:
        pass
