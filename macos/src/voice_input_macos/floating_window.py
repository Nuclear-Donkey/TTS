"""Frosted-glass floating status panel for macOS voice input.

Uses NSVisualEffectView (vibrancy material) for the Apple-style
translucent "毛玻璃" look.  Only shows a status dot + text —
microphone selection lives in the menu bar.
"""
from __future__ import annotations

import logging

import AppKit
import Foundation

log = logging.getLogger(__name__)

PANEL_WIDTH = 220.0
PANEL_HEIGHT = 48.0

# Colours
_RECORDING_DOT = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
    0.95, 0.33, 0.33, 1.0   # red
)
_PROCESSING_DOT = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
    1.0, 0.72, 0.2, 1.0     # amber
)
_TEXT_COLOR = AppKit.NSColor.whiteColor()


def _label(text: str, size: float, color: AppKit.NSColor) -> AppKit.NSTextField:
    lbl = AppKit.NSTextField.alloc().init()
    lbl.setStringValue_(text)
    lbl.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, AppKit.NSFontWeightMedium))
    lbl.setTextColor_(color)
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    return lbl


class FloatingWindow:
    """Borderless, always-on-top frosted-glass panel."""

    def __init__(self) -> None:
        # ── panel ──────────────────────────────────────────────
        self._panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT),
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._panel.setLevel_(AppKit.NSFloatingWindowLevel)
        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._panel.setHasShadow_(True)
        self._panel.setMovableByWindowBackground_(False)
        self._panel.setReleasedWhenClosed_(False)
        self._panel.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
        )

        content = self._panel.contentView()
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(14.0)
        content.layer().setMasksToBounds_(True)

        # ── frosted-glass backdrop ─────────────────────────────
        vibrancy = AppKit.NSVisualEffectView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT)
        )
        vibrancy.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        vibrancy.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        vibrancy.setState_(AppKit.NSVisualEffectStateActive)
        vibrancy.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
        vibrancy.setWantsLayer_(True)
        vibrancy.layer().setCornerRadius_(14.0)
        content.addSubview_(vibrancy)

        # ── status dot ─────────────────────────────────────────
        self._dot = _label("●", 16, _RECORDING_DOT)
        self._dot.setFrame_(Foundation.NSMakeRect(16, 12, 18, 24))
        content.addSubview_(self._dot)

        # ── status text ────────────────────────────────────────
        self._status = _label("", 14, _TEXT_COLOR)
        self._status.setFrame_(Foundation.NSMakeRect(38, 12, 170, 24))
        content.addSubview_(self._status)

        self._visible = False
        self._position()

    # ── public ────────────────────────────────────────────────

    def show(self, status: str, recording: bool = True) -> None:
        self._status.setStringValue_(status)
        color = _RECORDING_DOT if recording else _PROCESSING_DOT
        self._dot.setTextColor_(color)
        self._panel.makeKeyAndOrderFront_(None)
        self._visible = True

    def update_status(self, msg: str, recording: bool = True) -> None:
        self._status.setStringValue_(msg)
        color = _RECORDING_DOT if recording else _PROCESSING_DOT
        self._dot.setTextColor_(color)

    def hide(self) -> None:
        self._panel.orderOut_(None)
        self._visible = False

    @property
    def visible(self) -> bool:
        return self._visible

    # ── internals ──────────────────────────────────────────────

    def _position(self) -> None:
        screen = AppKit.NSScreen.mainScreen()
        if screen is None:
            return
        frame = screen.visibleFrame()
        x = frame.origin.x + (frame.size.width - PANEL_WIDTH) / 2
        y = frame.origin.y + frame.size.height - PANEL_HEIGHT - 20
        self._panel.setFrameOrigin_(Foundation.NSMakePoint(x, y))
