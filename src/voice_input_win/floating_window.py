"""Polished floating status panel for Windows voice input (PySide6).

Visual design:
    - Pill-shaped, 260 × 56, top-center, always on top, click-through.
    - Vertical gradient (deep blue → lighter blue) in recording state;
      amber gradient in processing / success.
    - Thin 1px light border, soft drop shadow (layered via QGraphicsEffect).
    - App icon on the left (uses bundled voice-input.ico), pulsing dot
      overlay while recording.
    - 180ms opacity fade on show / hide.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QLinearGradient,
    QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

PANEL_WIDTH = 260
PANEL_HEIGHT = 56
CORNER_RADIUS = 18
ICON_SIZE = 28
DOT_SIZE = 10
FADE_MS = 180

# ── palettes (match the app icon's dodger-blue scheme) ──────────────
_REC_TOP = QColor(79, 166, 255, 235)    # vivid blue top
_REC_BOT = QColor(30, 120, 215, 235)    # deeper blue bottom
_PROC_TOP = QColor(255, 196, 87, 235)   # warm amber top
_PROC_BOT = QColor(235, 150, 45, 235)   # deeper amber bottom
_ERR_TOP = QColor(255, 110, 110, 235)
_ERR_BOT = QColor(215, 60, 60, 235)
_BORDER = QColor(255, 255, 255, 70)
_TEXT = QColor(255, 255, 255, 240)
_SHADOW = QColor(0, 0, 0, 140)


def _bundled_icon() -> QIcon | None:
    """Find the packaged .ico (PyInstaller bundle or source tree)."""
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
        self._state = "recording"  # recording | processing | error
        self._icon = _bundled_icon()
        self._icon_pix = (
            self._icon.pixmap(QSize(ICON_SIZE, ICON_SIZE))
            if self._icon is not None else None
        )

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(PANEL_WIDTH, PANEL_HEIGHT + 14)  # extra room for shadow
        self._reposition()

        # Fade animation on window opacity
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Pulse animation for recording dot (scale 1.0 ↔ 1.35)
        self._pulse_phase = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._begin_fade_out)

    # ── public API ────────────────────────────────────────────────

    def show_recording(self) -> None:
        self._hide_timer.stop()
        self._state = "recording"
        self._text = "录音中…"
        self._reposition()
        self._fade_in()
        self._pulse_phase = 0.0
        self._pulse_timer.start(40)  # ~25fps
        self.update()

    def show_processing(self) -> None:
        self._hide_timer.stop()
        self._pulse_timer.stop()
        self._state = "processing"
        self._text = "识别中…"
        self.update()

    def show_success(self, text: str) -> None:
        self._pulse_timer.stop()
        preview = text if len(text) <= 28 else text[:28] + "…"
        self._state = "processing"
        self._text = f"✓  {preview}"
        self.update()
        self._hide_timer.start(1200)

    def show_error(self, msg: str) -> None:
        self._pulse_timer.stop()
        preview = msg if len(msg) <= 28 else msg[:28] + "…"
        self._state = "error"
        self._text = f"✗  {preview}"
        self.update()
        self._hide_timer.start(1800)

    def hide_panel(self) -> None:
        self._hide_timer.stop()
        self._pulse_timer.stop()
        self._begin_fade_out()

    # ── animation helpers ─────────────────────────────────────────

    def _fade_in(self) -> None:
        self.show()
        self.raise_()
        self._fade.stop()
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
        # Smooth sinusoidal pulse
        import math
        self._pulse_phase = (self._pulse_phase + 0.12) % (2 * math.pi)
        self.update()

    # ── drawing ───────────────────────────────────────────────────

    def _gradient_for_state(self) -> QLinearGradient:
        top, bot = {
            "recording": (_REC_TOP, _REC_BOT),
            "processing": (_PROC_TOP, _PROC_BOT),
            "error": (_ERR_TOP, _ERR_BOT),
        }[self._state]
        g = QLinearGradient(0, 0, 0, PANEL_HEIGHT)
        g.setColorAt(0.0, top)
        g.setColorAt(1.0, bot)
        return g

    def paintEvent(self, _evt) -> None:  # noqa: N802 (Qt API)
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Shadow: paint a soft dark rounded rect slightly offset below
        shadow_rect = QRectF(4, 8, PANEL_WIDTH - 8, PANEL_HEIGHT)
        shadow_color = QColor(_SHADOW)
        for i in range(6, 0, -1):
            shadow_color.setAlpha(12 * i)
            p.setBrush(QBrush(shadow_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(
                shadow_rect.adjusted(-i * 0.3, -i * 0.3, i * 0.3, i * 0.3 + i),
                CORNER_RADIUS + i * 0.5, CORNER_RADIUS + i * 0.5,
            )

        # Main pill
        body_rect = QRectF(0, 4, PANEL_WIDTH, PANEL_HEIGHT)
        p.setBrush(QBrush(self._gradient_for_state()))
        p.setPen(QPen(_BORDER, 1))
        p.drawRoundedRect(body_rect, CORNER_RADIUS, CORNER_RADIUS)

        # Left side: app icon
        content_y = 4
        if self._icon_pix is not None:
            icon_x = 16
            icon_y = content_y + (PANEL_HEIGHT - ICON_SIZE) // 2
            p.drawPixmap(icon_x, icon_y, self._icon_pix)
            text_x = icon_x + ICON_SIZE + 14
        else:
            text_x = 22

        # Recording: pulsing dot overlay on the icon's corner
        if self._state == "recording":
            scale = 1.0 + 0.35 * (0.5 + 0.5 * math.sin(self._pulse_phase))
            ds = int(DOT_SIZE * scale)
            cx = 16 + ICON_SIZE - ds // 2 + 2
            cy = content_y + (PANEL_HEIGHT - ICON_SIZE) // 2 - ds // 2 + 2
            # glow
            glow = QColor(255, 60, 60, 90)
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - 3, cy - 3, ds + 6, ds + 6)
            # solid dot
            p.setBrush(QBrush(QColor(255, 80, 80, 250)))
            p.drawEllipse(cx, cy, ds, ds)

        # Text
        p.setPen(_TEXT)
        font = QFont()
        font.setPointSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        fm = QFontMetrics(font)
        text_y = content_y + (PANEL_HEIGHT + fm.ascent() - fm.descent()) // 2
        p.drawText(int(text_x), int(text_y), self._text)

    # ── positioning ───────────────────────────────────────────────

    def _reposition(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - PANEL_WIDTH) // 2
        y = geo.y() + 28
        self.move(QPoint(x, y))
