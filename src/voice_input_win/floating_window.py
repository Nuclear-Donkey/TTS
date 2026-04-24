"""Apple-style dark HUD floating panel (PySide6, Windows).

Design intent mirrors macOS HUDWindow / Spotlight:
    - Near-black translucent fill (rgba 28,28,30,215)
    - True backdrop blur via DWM SetWindowCompositionAttribute when available
    - Generous 20px corner radius
    - Hairline light border (1px rgba 255,255,255,28)
    - Multi-stop soft shadow
    - Colour is constant; only the status glyph (● recording /
      ◼ processing / ✓ success / ✗ error) changes
    - 120ms ease-out opacity fade
    - Positioning delegated to caret_locator (caret first, mouse fallback)
"""
from __future__ import annotations

import logging
import math
import sys
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from voice_input_win.caret_locator import locate

log = logging.getLogger(__name__)

PANEL_WIDTH = 240
PANEL_HEIGHT = 46
CORNER_RADIUS = 20
SHADOW_EXTRA = 16           # extra height for shadow bleed
FADE_MS = 120

# ── palette (constant, Apple-dark-HUD style) ─────────────────────────
_BG = QColor(28, 28, 30, 215)
_BORDER = QColor(255, 255, 255, 28)
_TEXT = QColor(255, 255, 255, 235)
_TEXT_DIM = QColor(255, 255, 255, 160)
_DOT_REC = QColor(255, 90, 95)       # soft red
_DOT_PROC = QColor(255, 197, 66)     # soft amber
_DOT_OK = QColor(88, 212, 124)       # soft green
_DOT_ERR = QColor(255, 100, 100)
_SHADOW = QColor(0, 0, 0, 120)


# ── Win32 backdrop blur helper ───────────────────────────────────────

def _enable_blur_behind(hwnd: int) -> None:
    """Use undocumented DWM APIs to blur the background behind our panel.
    Gracefully no-ops if the API isn't available (non-Win10+, etc.).
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class ACCENT_POLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_int),
                ("AnimationId", ctypes.c_int),
            ]

        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.POINTER(ACCENT_POLICY)),
                ("SizeOfData", ctypes.c_size_t),
            ]

        # ACCENT_ENABLE_ACRYLICBLURBEHIND = 4  (Win10 1803+)
        # ACCENT_ENABLE_BLURBEHIND = 3         (Win10 ≤ 1709)
        accent = ACCENT_POLICY()
        accent.AccentState = 4
        accent.AccentFlags = 0
        accent.GradientColor = 0  # alpha=0 → don't tint (we paint our own)
        accent.AnimationId = 0

        data = WINCOMPATTRDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.SizeOfData = ctypes.sizeof(accent)
        data.Data = ctypes.pointer(accent)

        user32 = ctypes.windll.user32
        SetWindowCompositionAttribute = user32.SetWindowCompositionAttribute
        SetWindowCompositionAttribute.argtypes = [
            wintypes.HWND, ctypes.POINTER(WINCOMPATTRDATA)
        ]
        SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
    except Exception:
        log.debug("acrylic blur setup failed (non-fatal)", exc_info=True)


def _bundled_icon() -> QIcon | None:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(
            Path(sys._MEIPASS) / "resources" / "icons" / "voice-input.ico"  # type: ignore[attr-defined]
        )
    here = Path(__file__).resolve()
    candidates.append(here.parents[2] / "resources" / "icons" / "voice-input.ico")
    for c in candidates:
        if c.exists():
            return QIcon(str(c))
    return None


class FloatingWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._text = ""
        self._state = "recording"
        self._icon = _bundled_icon()
        icon_size = 22
        self._icon_pix = (
            self._icon.pixmap(QSize(icon_size, icon_size))
            if self._icon is not None else None
        )
        self._icon_size = icon_size

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(PANEL_WIDTH, PANEL_HEIGHT + SHADOW_EXTRA)

        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._pulse_phase = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)

        self._blur_enabled = False

    # ── public API ──────────────────────────────────────────────

    def show_recording(self) -> None:
        self._state = "recording"
        self._text = "按住 Caps Lock 说话"
        self._reposition()
        self._fade_in()
        self._pulse_phase = 0.0
        self._pulse_timer.start(40)
        self.update()

    def show_processing(self) -> None:
        self._pulse_timer.stop()
        self._state = "processing"
        self._text = "识别中…"
        self.update()

    def show_success(self, text: str) -> None:
        # Briefly flash the result — caller decides whether to show this
        # depending on the UX flow. Hidden automatically after a short delay.
        self._pulse_timer.stop()
        preview = text if len(text) <= 24 else text[:24] + "…"
        self._state = "success"
        self._text = preview
        self._reposition()
        self._fade_in()
        QTimer.singleShot(900, self.hide_panel)
        self.update()

    def show_error(self, msg: str) -> None:
        self._pulse_timer.stop()
        preview = msg if len(msg) <= 24 else msg[:24] + "…"
        self._state = "error"
        self._text = preview
        self._reposition()
        self._fade_in()
        QTimer.singleShot(1400, self.hide_panel)
        self.update()

    def hide_panel(self) -> None:
        self._pulse_timer.stop()
        self._begin_fade_out()

    # ── animation ───────────────────────────────────────────────

    def _fade_in(self) -> None:
        self.show()
        self.raise_()
        if not self._blur_enabled:
            try:
                _enable_blur_behind(int(self.winId()))
                self._blur_enabled = True
            except Exception:
                pass
        self._fade.stop()
        try:
            self._fade.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _begin_fade_out(self) -> None:
        if not self.isVisible():
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        try:
            self._fade.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._fade.finished.connect(self.hide)
        self._fade.start()

    def _tick_pulse(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.14) % (2 * math.pi)
        self.update()

    # ── drawing ─────────────────────────────────────────────────

    def _dot_color(self) -> QColor:
        return {
            "recording": _DOT_REC,
            "processing": _DOT_PROC,
            "success": _DOT_OK,
            "error": _DOT_ERR,
        }[self._state]

    def paintEvent(self, _evt) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Soft shadow (layered rounded rects under the body)
        body_top = 2
        shadow_color = QColor(_SHADOW)
        for i in range(6, 0, -1):
            shadow_color.setAlpha(10 * i)
            p.setBrush(QBrush(shadow_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(
                QRectF(
                    -i * 0.6, body_top + i * 0.6,
                    PANEL_WIDTH + i * 1.2, PANEL_HEIGHT + i * 1.2,
                ),
                CORNER_RADIUS + i * 0.4, CORNER_RADIUS + i * 0.4,
            )

        # Body fill (acrylic will show through alpha; we still fill
        # because blur might not be enabled on older Windows)
        body_rect = QRectF(0, body_top, PANEL_WIDTH, PANEL_HEIGHT)
        p.setBrush(QBrush(_BG))
        p.setPen(QPen(_BORDER, 0.75))
        p.drawRoundedRect(body_rect, CORNER_RADIUS, CORNER_RADIUS)

        # Status dot (left)
        dot_d = 9
        cx = 20
        cy = body_top + PANEL_HEIGHT // 2 - dot_d // 2
        if self._state == "recording":
            # breathing glow
            glow_t = 0.5 + 0.5 * math.sin(self._pulse_phase)
            glow = QColor(self._dot_color())
            glow.setAlpha(int(50 + 80 * glow_t))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            halo = int(6 + 4 * glow_t)
            p.drawEllipse(cx - halo // 2, cy - halo // 2,
                          dot_d + halo, dot_d + halo)

        p.setBrush(QBrush(self._dot_color()))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx, cy, dot_d, dot_d)

        # Label text
        text_x = cx + dot_d + 12
        font = QFont()
        # SF / system font — on Windows falls back to Segoe UI, which is
        # the closest native equivalent.
        font.setFamily("Segoe UI")
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(_TEXT)
        fm = QFontMetrics(font)
        text_y = body_top + (PANEL_HEIGHT + fm.ascent() - fm.descent()) // 2
        p.drawText(int(text_x), int(text_y), self._text)

    # ── positioning ─────────────────────────────────────────────

    def _reposition(self) -> None:
        x, y = locate(PANEL_WIDTH, PANEL_HEIGHT + SHADOW_EXTRA)
        self.move(QPoint(x, y))
