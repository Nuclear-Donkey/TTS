"""Entry point for macOS voice input.

Run:  python -m voice_input_macos
      python -m voice_input_macos --debug

Shows a menu-bar item with mic selector.  Hold the configured hotkey
(caps_lock by default) and a frosted-glass floating panel appears.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

import AppKit
import Foundation
import objc

from voice_input_macos import config as cfg_mod
from voice_input_macos.accessibility import check_accessibility, prompt_accessibility
from voice_input_macos.floating_window import FloatingWindow
from voice_input_macos.hotkey import HotkeyController, State
from voice_input_macos.paths import CONFIG_FILE, LOG_DIR, LOG_FILE
from shared.audio import Recorder, RecorderError, list_input_devices
from shared.stt import ParaformerStt, SttError


# ── logging ───────────────────────────────────────────────────

def _setup_logging(debug: bool) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def _print_banner(cfg) -> None:
    has_accessibility = check_accessibility()
    print()
    print("=" * 60)
    print("  voice-input for macOS")
    print("=" * 60)
    print(f"  hotkey:       hold  [{cfg.hotkey.ptt}]  to talk")
    print(f"  model dir:    {cfg.stt.model_dir}")
    print(f"  audio device: {cfg.audio.device or '(system default)'}")
    print(f"  inject:       {cfg.inject.method}")
    print(f"  log:          {LOG_FILE}")
    print(f"  config:       {CONFIG_FILE}")
    print(f"  accessibility: {'granted' if has_accessibility else 'NOT granted'}")
    print("=" * 60)
    print()


# ── menu bar ──────────────────────────────────────────────────

class _MenuBar(Foundation.NSObject):
    """NSStatusBar item with mic-selection menu."""

    _recorder = objc.ivar(type=objc._C_ID)
    _devices = objc.ivar(type=objc._C_ID)
    _device_items = objc.ivar(type=objc._C_ID)
    _menu = objc.ivar(type=objc._C_ID)
    _device_cfg = objc.ivar(type=objc._C_ID)
    _log = objc.ivar(type=objc._C_ID)

    def init(self):
        self = objc.super(_MenuBar, self).init()
        if self is not None:
            self._recorder = None
            self._devices = []
            self._device_items = []
            self._menu = None
            self._device_cfg = ""
            self._log = None
        return self

    def setupWithDevices_currentDevice_(self, devices, current):
        status_bar = AppKit.NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(
            AppKit.NSVariableStatusItemLength
        )
        self._status_item.setTitle_(" MIC ")
        self._status_item.setHighlightMode_(True)

        self._menu = AppKit.NSMenu.alloc().init()

        # "正在监听" header
        header = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "正在监听...", None, ""
        )
        header.setEnabled_(False)
        self._menu.addItem_(header)
        self._menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # Mic section
        mic_header = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "麦克风", None, ""
        )
        mic_header.setEnabled_(False)
        self._menu.addItem_(mic_header)

        self._devices = devices
        self._device_cfg = current
        self._device_items = []
        for d in devices:
            item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                d["name"], objc.selector(self._selectDevice_, signature=b"v@:@"), ""
            )
            item.setTag_(d["index"])
            item.setTarget_(self)
            self._menu.addItem_(item)
            self._device_items.append(item)

        self._checkCurrentDevice()

        self._menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # Accessibility
        acc_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "授予辅助功能权限…",
            objc.selector(self._requestAccessibility_, signature=b"v@:@"),
            "",
        )
        acc_item.setTarget_(self)
        self._menu.addItem_(acc_item)

        # Quit
        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "退出",
            objc.selector(self._quit_, signature=b"v@:@"),
            "q",
        )
        quit_item.setTarget_(self)
        self._menu.addItem_(quit_item)

        self._status_item.setMenu_(self._menu)

    def _selectDevice_(self, sender):
        name = str(sender.title())
        if self._recorder is not None:
            self._recorder.device_cfg = name
        self._device_cfg = name
        if self._log:
            self._log.info("mic switched to: %s", name)
        self._checkCurrentDevice()

    def _checkCurrentDevice(self):
        """Add ✓ to the current device menu item (match by stored item list)."""
        current = (self._device_cfg or "").strip().lower()
        for item in self._device_items:
            name = str(item.title()).strip().lower()
            on = AppKit.NSControlStateValueOn
            off = AppKit.NSControlStateValueOff
            item.setState_(on if name == current else off)

    def _requestAccessibility_(self, sender):
        prompt_accessibility()

    def _quit_(self, sender):
        AppKit.NSApp().terminate_(None)


# ── state bridge ──────────────────────────────────────────────

class _StateBridge(Foundation.NSObject):
    """Forwards state changes from pynput thread → main thread."""

    _window = objc.ivar(type=objc._C_ID)
    _log = objc.ivar(type=objc._C_ID)

    def init(self):
        self = objc.super(_StateBridge, self).init()
        if self is not None:
            self._window = None
            self._log = None
        return self

    def onStateChange_(self, state_name):
        s = str(state_name)
        win = self._window
        if win is None:
            return
        # Preview of the recognised text is sent as "text:<content>".
        if s.startswith("text:"):
            preview = s[5:]
            if preview:
                preview = preview[:30] + ("…" if len(preview) > 30 else "")
                win.show(f"✓ {preview}", recording=False)
                # Auto-hide after ~1s so the user sees confirmation.
                Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    1.0, self, objc.selector(self._hide_, signature=b"v@:@"), None, False
                )
            return
        try:
            state = State(s)
        except ValueError:
            return
        if state is State.RECORDING:
            win.show("录音中…", recording=True)
        elif state is State.PROCESSING:
            win.update_status("识别中…", recording=False)
        elif state is State.IDLE:
            win.hide()

    def _hide_(self, _timer):
        if self._window is not None:
            self._window.hide()


# ── main ──────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(prog="voice-input-macos")
    parser.add_argument("--debug", action="store_true", help="verbose logs")
    args = parser.parse_args()

    _setup_logging(args.debug or os.getenv("VOICE_INPUT_DEBUG") == "1")
    log = logging.getLogger("voice_input_macos.main")
    log.info("=" * 60)
    log.info("starting voice-input-macos (pid=%d)", os.getpid())

    cfg = cfg_mod.load()
    _print_banner(cfg)

    # ── accessibility ─────────────────────────────────────────
    has_acc = check_accessibility()
    inject_method = cfg.inject.method
    if not has_acc:
        log.warning(
            "Accessibility permission not granted — neither 'paste' nor "
            "'applescript' will work until you enable it in "
            "System Settings > Privacy & Security > Accessibility."
        )
        prompt_accessibility()
        has_acc = check_accessibility()
        if not has_acc:
            print(
                "WARNING: Accessibility permission missing. Hotkey capture "
                "and paste will fail. Enable it for your terminal "
                "(or packaged app) and re-run.",
                file=sys.stderr,
            )

    # ── STT + recorder ────────────────────────────────────────
    try:
        stt = ParaformerStt(cfg.stt.model_dir, num_threads=cfg.stt.num_threads)
    except SttError as e:
        log.error("%s", e)
        print(f"ERROR: {e}")
        print("Run:  python scripts/download-model.py --small")
        return 2

    try:
        recorder = Recorder(device=cfg.audio.device)
    except RecorderError as e:
        log.error("%s", e)
        print(f"ERROR: {e}")
        return 2

    # ── Cocoa setup ───────────────────────────────────────────
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyProhibited)

    devices = list_input_devices()
    log.info("input devices: %s", [d["name"] for d in devices])

    # Floating window
    window = FloatingWindow()

    # Menu bar
    menubar = _MenuBar.alloc().init()
    menubar._recorder = recorder
    menubar._log = log
    menubar.setupWithDevices_currentDevice_(devices, cfg.audio.device)

    # State bridge
    bridge = _StateBridge.alloc().init()
    bridge._window = window
    bridge._log = log

    # ── hotkey controller ─────────────────────────────────────
    def _on_status(msg: str) -> None:
        try:
            sys.stderr.write(f"  {msg}\n")
            sys.stderr.flush()
        except (BrokenPipeError, OSError):
            pass

    def _on_state_change(state: State) -> None:
        bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(bridge.onStateChange_, signature=b"v@:@"),
            Foundation.NSString.stringWithString_(state.value),
            False,
        )

    def _on_text(text: str) -> None:
        bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(bridge.onStateChange_, signature=b"v@:@"),
            Foundation.NSString.stringWithString_(f"text:{text}"),
            False,
        )

    controller = HotkeyController(
        ptt_key=cfg.hotkey.ptt,
        recorder=recorder,
        stt=stt,
        inject_method=inject_method,
        restore_clipboard=cfg.inject.restore_clipboard,
        paste_delay=cfg.inject.paste_delay,
        on_status=_on_status,
        on_state_change=_on_state_change,
        on_text=_on_text,
    )

    # ── signal handling ───────────────────────────────────────
    _shutdown = False

    def _sig(_signum, _frame):
        nonlocal _shutdown
        _shutdown = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    # ── run ───────────────────────────────────────────────────
    controller.start()
    log.info("main loop starting")

    try:
        run_loop = Foundation.NSRunLoop.currentRunLoop()
        while not _shutdown:
            run_loop.runMode_beforeDate_(
                AppKit.NSDefaultRunLoopMode,
                Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1),
            )
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        window.hide()
        log.info("main loop exited")

    return 0


if __name__ == "__main__":
    sys.exit(main())
