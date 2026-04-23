"""System tray icon + right-click menu for Windows voice input.

Menu:
    正在监听 [right alt]           (header, disabled)
    ───────
    麦克风 ▸
        ✓ Microphone (Realtek...)
          USB Headset
          ...
    ───────
    打开配置文件
    打开日志文件夹
    退出
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QPainter, QPixmap, QColor, QBrush
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QApplication

from voice_input_win.paths import CONFIG_FILE, LOG_DIR

log = logging.getLogger(__name__)


def _make_icon() -> QIcon:
    """Fall back to a programmatic microphone glyph when the bundled .ico
    isn't available at runtime (e.g. dev mode). In frozen builds we use
    the bundled resources/icons/voice-input.ico.
    """
    import sys
    from pathlib import Path
    # Try bundled ICO first.
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

    # Fallback: draw one.
    size = 64
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(30, 144, 255)))
    p.drawRoundedRect(20, 10, 24, 30, 12, 12)
    p.drawRect(30, 44, 4, 10)
    p.drawRect(20, 52, 24, 4)
    p.end()
    return QIcon(pix)


class TrayIcon(QObject):
    def __init__(
        self,
        *,
        app: QApplication,
        ptt_key: str,
        devices: list[dict],
        current_device: str,
        on_device_change: Callable[[str], None],
        on_quit: Callable[[], None],
    ) -> None:
        super().__init__()
        self._app = app
        self._on_device_change = on_device_change
        self._on_quit = on_quit
        self._devices = devices

        self._tray = QSystemTrayIcon(_make_icon())
        self._tray.setToolTip(f"voice-input  [按住 {ptt_key} 说话]")

        self._menu = QMenu()

        header = QAction(f"正在监听  [{ptt_key}]", self._menu)
        header.setEnabled(False)
        self._menu.addAction(header)
        self._menu.addSeparator()

        # Mic submenu
        mic_menu = self._menu.addMenu("麦克风")
        group = QActionGroup(self)
        group.setExclusive(True)
        current_lc = (current_device or "").strip().lower()
        self._device_actions: list[QAction] = []
        for d in devices:
            name = d["name"]
            act = QAction(name, mic_menu)
            act.setCheckable(True)
            if name.strip().lower() == current_lc or (
                not current_lc and d.get("is_default")
            ):
                act.setChecked(True)
            act.triggered.connect(lambda _c=False, n=name: self._select_device(n))
            group.addAction(act)
            mic_menu.addAction(act)
            self._device_actions.append(act)

        self._menu.addSeparator()

        open_cfg = QAction("打开配置文件", self._menu)
        open_cfg.triggered.connect(lambda: _open_path(CONFIG_FILE))
        self._menu.addAction(open_cfg)

        open_log = QAction("打开日志文件夹", self._menu)
        open_log.triggered.connect(lambda: _open_path(LOG_DIR))
        self._menu.addAction(open_log)

        self._menu.addSeparator()

        quit_act = QAction("退出", self._menu)
        quit_act.triggered.connect(self._on_quit)
        self._menu.addAction(quit_act)

        self._tray.setContextMenu(self._menu)
        self._tray.show()

    def notify(self, title: str, msg: str, ms: int = 2000) -> None:
        self._tray.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, ms)

    def _select_device(self, name: str) -> None:
        log.info("tray: mic switched to %s", name)
        for act in self._device_actions:
            act.setChecked(act.text() == name)
        try:
            self._on_device_change(name)
        except Exception:
            log.exception("device change callback failed")


def _open_path(path: Path) -> None:
    try:
        if path.is_file():
            os.startfile(str(path))  # noqa: S606 (Windows only)
        else:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))  # noqa: S606
    except AttributeError:
        # Not Windows — fallback for dev
        subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        log.exception("open path failed: %s", path)
