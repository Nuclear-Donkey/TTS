"""Entry point for Windows voice input.

Run:  py -m voice_input_win              (as Administrator recommended)
      py -m voice_input_win --debug
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from voice_input_win import config as cfg_mod
from voice_input_win.hotkey import HotkeyController
from voice_input_win.paths import CONFIG_FILE, LOG_DIR, LOG_FILE, MODEL_DIR
from voice_input_win.recorder import Recorder, RecorderError
from voice_input_win.stt import ParaformerStt, SttError


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
    print()
    print("=" * 60)
    print("  voice-input for Windows")
    print("=" * 60)
    print(f"  hotkey:       hold  [{cfg.hotkey.ptt}]  to talk")
    print(f"  model dir:    {cfg.stt.model_dir}")
    print(f"  audio device: {cfg.audio.device or '(system default)'}")
    print(f"  inject:       {cfg.inject.method}")
    print(f"  log:          {LOG_FILE}")
    print(f"  config:       {CONFIG_FILE}")
    print("=" * 60)
    print()
    # Warn users running as non-admin — keyboard hooks may miss events from
    # elevated windows.
    try:
        import ctypes
        admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        admin = False
    if not admin:
        print("  ⚠  Not running as Administrator.")
        print("     Hotkey may be suppressed in elevated windows (Task Manager,")
        print("     some game launchers). Start via 'run-as-admin.bat' for best.")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(prog="voice-input-win")
    parser.add_argument("--debug", action="store_true", help="verbose logs")
    args = parser.parse_args()

    _setup_logging(args.debug or os.getenv("VOICE_INPUT_DEBUG") == "1")
    log = logging.getLogger("voice_input_win.main")
    log.info("=" * 60)
    log.info("starting voice-input-win (pid=%d)", os.getpid())

    cfg = cfg_mod.load()
    _print_banner(cfg)

    try:
        stt = ParaformerStt(cfg.stt.model_dir, num_threads=cfg.stt.num_threads)
    except SttError as e:
        log.error("%s", e)
        print(f"ERROR: {e}")
        print("Run:  py scripts\\download_model.py")
        return 2

    try:
        recorder = Recorder(device=cfg.audio.device)
    except RecorderError as e:
        log.error("%s", e)
        print(f"ERROR: {e}")
        return 2

    def _on_status(msg: str) -> None:
        # Single console line, overwrite in place.
        sys.stdout.write(f"\r  {msg:<78}\r")
        sys.stdout.flush()

    controller = HotkeyController(
        ptt_key=cfg.hotkey.ptt,
        recorder=recorder,
        stt=stt,
        restore_clipboard=cfg.inject.restore_clipboard,
        paste_delay=cfg.inject.paste_delay,
        on_status=_on_status,
    )

    def _sig(_signum, _frame):
        print("\nshutting down…")
        controller.stop()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    try:
        controller.run()
    except Exception:
        log.exception("controller crashed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
