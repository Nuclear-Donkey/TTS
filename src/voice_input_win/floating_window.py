"""Frosted-glass floating status panel for Windows voice input.

Top-center borderless panel, always on top, click-through (WS_EX_TRANSPARENT),
draws a status dot + text over a translucent rounded rectangle.

Three visual states mirror the macOS panel:
    RECORDING   — red dot, text "录音中…"
    PROCESSING  — amber dot, text "识别中…"
    SUCCESS     — amber dot, text "✓ <preview>"  auto-hide after 1s
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, QRectF, QPoint
from PySide6.QtGui import QColor, QPainter, QBrush, QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

PANEL_WIDTH = 240
PANEL_HEIGHT = 52
CORNER_RADIUS = 14

_BG = QColor(28, 28, 30, 220)        # near-black translucent
_TEXT = QColor(255, 255, 255, 235)
_DOT_RECORD = QColor(242, 84, 84)    # red
_DOT_PROCESS = QColor(255, 184, 51)  # amber


class FloatingWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._text = ""
        self._dot_color = _DOT_RECORD

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool              # no taskbar entry
            | Qt.WindowType.WindowTransparentForInput  # click-through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(PANEL_WIDTH, PANEL_HEIGHT)
        self._reposition()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    # ── public API ────────────────────────────────────────────────

    def show_recording(self) -> None:
        self._hide_timer.stop()
        self._dot_color = _DOT_RECORD
        self._text = "录音中…"
        self._reposition()
        self.show()
        self.raise_()
        self.update()

    def show_processing(self) -> None:
        self._hide_timer.stop()
        self._dot_color = _DOT_PROCESS
        self._text = "识别中…"
        self.update()

    def show_success(self, text: str) -> None:
        preview = text if len(text) <= 28 else text[:28] + "…"
        self._dot_color = _DOT_PROCESS
        self._text = f"✓ {preview}"
        self.update()
        self._hide_timer.start(1000)

    def show_error(self, msg: str) -> None:
        preview = msg if len(msg) <= 28 else msg[:28] + "…"
        self._dot_color = _DOT_RECORD
        self._text = f"✗ {preview}"
        self.update()
        self._hide_timer.start(1500)

    def hide_panel(self) -> None:
        self._hide_timer.stop()
        self.hide()

    # ── internals ─────────────────────────────────────────────────

    def _reposition(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - PANEL_WIDTH) // 2
        y = geo.y() + 24
        self.move(QPoint(x, y))

    def paintEvent(self, _evt) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background rounded rect
        p.setBrush(QBrush(_BG))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(
            QRectF(0, 0, self.width(), self.height()),
            CORNER_RADIUS, CORNER_RADIUS,
        )

        # Dot
        p.setBrush(QBrush(self._dot_color))
        dot_size = 10
        dot_x = 18
        dot_y = (self.height() - dot_size) // 2
        p.drawEllipse(dot_x, dot_y, dot_size, dot_size)

        # Text
        p.setPen(_TEXT)
        font = QFont()
        font.setPointSize(11)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        fm = QFontMetrics(font)
        text_x = dot_x + dot_size + 12
        text_y = (self.height() + fm.ascent() - fm.descent()) // 2
        p.drawText(text_x, text_y, self._text)
