"""Entry point for Windows voice input (GUI mode, no console).

Qt event loop runs on the main thread; hotkey listener runs on a
background thread (the `keyboard` library's own thread), and state
transitions cross back via Qt signals to update the floating window
and tray icon.

Launched by a shortcut / Start-menu entry — no terminal window shown
(when packaged with PyInstaller --windowed).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from voice_input_win import config as cfg_mod
from voice_input_win.first_run import run_if_needed
from voice_input_win.floating_window import FloatingWindow
from voice_input_win.hotkey import HotkeyController, State
from voice_input_win.paths import CONFIG_FILE, CONFIG_DIR, LOG_DIR, LOG_FILE
from voice_input_win.recorder import Recorder, RecorderError
from voice_input_win.stt import ParaformerStt, SttError
from voice_input_win.tray import TrayIcon
from voice_input_common.audio import list_input_devices


# ── logging (file-only by default; no console handler in GUI mode) ──

def _setup_logging(debug: bool) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = [
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
    # Only add stderr handler if we actually have a console attached.
    if sys.stderr and sys.stderr.isatty():
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


# ── bridge: hotkey thread  →  Qt main thread ────────────────────────

class _StateBridge(QObject):
    """Signals emitted from hotkey thread, handled on main thread."""

    state_changed = Signal(str)   # "recording" / "processing" / "idle"
    text_ready = Signal(str)      # recognised text (post-paste)
    error_occurred = Signal(str)  # user-facing error message


# ── first-run check ─────────────────────────────────────────────────

def _ensure_config_seeded() -> None:
    """Copy default config on first run."""
    if CONFIG_FILE.exists():
        return
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Look in several places where the default config might live after
    # PyInstaller bundling.
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(
            os.path.join(sys._MEIPASS, "resources", "default-config-win.toml")  # type: ignore[attr-defined]
        )
    # Dev mode
    from pathlib import Path as _P
    here = _P(__file__).resolve()
    candidates.append(str(here.parents[2] / "resources" / "default-config-win.toml"))
    for c in candidates:
        if os.path.exists(c):
            import shutil
            shutil.copy(c, CONFIG_FILE)
            logging.info("seeded default config to %s", CONFIG_FILE)
            return
    logging.warning("no default-config-win.toml bundled — config not seeded")


# ── main ────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(prog="voice-input-win")
    parser.add_argument("--debug", action="store_true", help="verbose logs")
    args, _ = parser.parse_known_args()

    _setup_logging(args.debug or os.getenv("VOICE_INPUT_DEBUG") == "1")
    log = logging.getLogger("voice_input_win.main")
    log.info("=" * 60)
    log.info("starting voice-input-win GUI (pid=%d)", os.getpid())

    _ensure_config_seeded()
    cfg = cfg_mod.load()

    # Qt application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray-only app

    # Tray must be available
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None, "voice-input",
            "当前系统没有可用的任务栏托盘区，程序无法启动。"
        )
        return 1

    # First-run: download model if missing, create shortcuts.
    from pathlib import Path as _P
    if not run_if_needed(_P(cfg.stt.model_dir).expanduser()):
        return 2

    # STT
    try:
        stt = ParaformerStt(cfg.stt.model_dir, num_threads=cfg.stt.num_threads)
    except SttError as e:
        log.exception("STT init failed")
        QMessageBox.critical(None, "voice-input", f"识别引擎加载失败:\n{e}")
        return 2

    # Recorder
    try:
        recorder = Recorder(device=cfg.audio.device)
    except RecorderError as e:
        log.exception("recorder init failed")
        QMessageBox.critical(None, "voice-input", f"麦克风初始化失败:\n{e}")
        return 2

    # UI pieces
    window = FloatingWindow()
    bridge = _StateBridge()

    @Slot(str)
    def _on_state(name: str) -> None:
        # Panel shows only while the PTT key is held. Pressing =
        # RECORDING → show; releasing = PROCESSING → hide immediately.
        # The recognised text arrives asynchronously via _on_text and
        # is delivered as a tray balloon instead of a panel flash.
        if name == State.RECORDING.value:
            window.show_recording()
        else:
            window.hide_panel()

    @Slot(str)
    def _on_text(text: str) -> None:
        # Tray notification instead of panel — panel is already gone.
        preview = text if len(text) <= 40 else text[:40] + "…"
        tray.notify("voice-input", f"✓ {preview}", 1400)

    @Slot(str)
    def _on_err(msg: str) -> None:
        tray.notify("voice-input", f"✗ {msg}", 2000)

    # Devices
    devices = list_input_devices()
    log.info("input devices: %s", [d["name"] for d in devices])

    def _change_device(name: str) -> None:
        recorder.device_cfg = name
        log.info("device switched (will take effect on next recording): %s", name)

    def _quit() -> None:
        log.info("quit requested via tray")
        app.quit()

    tray = TrayIcon(
        app=app,
        ptt_key=cfg.hotkey.ptt,
        devices=devices,
        current_device=cfg.audio.device,
        on_device_change=_change_device,
        on_quit=_quit,
    )

    # Wire bridge callbacks after tray exists (they reference it).
    bridge.state_changed.connect(_on_state)
    bridge.text_ready.connect(_on_text)
    bridge.error_occurred.connect(_on_err)

    # Hotkey controller on background thread
    controller = HotkeyController(
        ptt_key=cfg.hotkey.ptt,
        recorder=recorder,
        stt=stt,
        restore_clipboard=cfg.inject.restore_clipboard,
        paste_delay=cfg.inject.paste_delay,
        suppress_caps_lock_toggle=cfg.hotkey.suppress_caps_lock_toggle,
        on_status=lambda s: log.debug("status: %s", s),
        on_state_change=lambda st: bridge.state_changed.emit(st.value),
        on_text=lambda t: bridge.text_ready.emit(t),
        on_error=lambda m: bridge.error_occurred.emit(m),
    )

    def _hotkey_thread() -> None:
        try:
            controller.run()
        except Exception as e:
            log.exception("hotkey controller crashed")
            bridge.error_occurred.emit(f"热键注册失败: {e}")

    t = threading.Thread(target=_hotkey_thread, daemon=True, name="hotkey")
    t.start()

    # Greet
    QTimer.singleShot(
        500,
        lambda: tray.notify(
            "voice-input 已启动",
            f"按住 [{cfg.hotkey.ptt}] 说话，松开后文字自动粘贴。",
        ),
    )

    # Admin warning (notification, not terminal)
    try:
        import ctypes
        admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        admin = True
    if not admin:
        QTimer.singleShot(
            1500,
            lambda: tray.notify(
                "提示",
                "当前非管理员运行，在部分提权窗口中可能无法响应热键。",
                3500,
            ),
        )

    # Event loop
    rc = app.exec()
    controller.stop()
    log.info("exited with rc=%d", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
