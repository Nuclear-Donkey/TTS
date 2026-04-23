"""macOS Accessibility permission helpers.

AXIsProcessTrusted / AXIsProcessTrustedWithOptions live in the
ApplicationServices framework. On PyObjC they're exposed under the
HIServices submodule. We import defensively so a missing framework
gives a clear message rather than ImportError at module load.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

try:
    import HIServices  # type: ignore[import-not-found]
except ImportError:
    HIServices = None  # type: ignore[assignment]
    log.warning(
        "HIServices not importable — install 'pyobjc-framework-ApplicationServices'"
    )


def check_accessibility() -> bool:
    """Check whether this process has Accessibility permission."""
    if HIServices is None:
        return False
    try:
        return bool(HIServices.AXIsProcessTrusted())
    except Exception:
        log.exception("AXIsProcessTrusted failed")
        return False


def prompt_accessibility() -> None:
    """Trigger the macOS Accessibility permission dialog."""
    if HIServices is None:
        return
    try:
        HIServices.AXIsProcessTrustedWithOptions(
            {HIServices.kAXTrustedCheckOptionPrompt: True}
        )
    except Exception:
        log.exception("AXIsProcessTrustedWithOptions failed")
