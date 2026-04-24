"""Entry point: load config + STT once, register VoiceEngine, run GLib loop.

Invoked by IBus daemon via the <exec> in the component XML:
    python -m voice_ibus --ibus
Or standalone for development (no --ibus): registers the same bus name, and
IBus will use this process for the 'voice' engine as long as the component
XML is installed.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus

from voice_ibus import config as cfg_mod
from voice_ibus.engine import VoiceEngine
from voice_ibus.stt import ParaformerStt, SttError

LOG_DIR = Path(os.path.expanduser("~/.cache/ibus-voice"))
LOG_FILE = LOG_DIR / "service.log"

BUS_NAME = "org.freedesktop.IBus.Voice"
ENGINE_NAME = "voice"
COMPONENT_NAME = "org.freedesktop.IBus.Voice"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if os.getenv("VOICE_IBUS_DEBUG") == "1" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stderr),
        ],
    )


def _build_component() -> IBus.Component:
    comp = IBus.Component(
        name=COMPONENT_NAME,
        description="Voice input (Paraformer local STT)",
        version="0.1.0",
        license="MIT",
        author="zs",
        homepage="",
        command_line="",
        textdomain="voice-ibus",
    )
    engine = IBus.EngineDesc(
        name=ENGINE_NAME,
        longname="Voice",
        description="Push-to-talk voice input (中文 Paraformer)",
        language="zh",
        license="MIT",
        author="zs",
        icon="audio-input-microphone",
        layout="default",
    )
    comp.add_engine(engine)
    return comp


def _load_stt(cfg) -> ParaformerStt | None:
    model_dir = os.path.expanduser(cfg.stt.model_dir)
    try:
        return ParaformerStt(model_dir, num_threads=cfg.stt.num_threads)
    except SttError as e:
        logging.getLogger("voice_ibus.main").error("STT load failed: %s", e)
        logging.getLogger("voice_ibus.main").error(
            "Run: .venv/bin/python scripts/download-model.py"
        )
        return None
    except Exception:
        logging.getLogger("voice_ibus.main").exception("unexpected STT load error")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(prog="voice-ibus")
    parser.add_argument("--ibus", action="store_true",
                        help="Run under IBus daemon")
    args = parser.parse_args()

    _setup_logging()
    log = logging.getLogger("voice_ibus.main")
    log.info("=" * 60)
    log.info("starting voice-ibus (ibus=%s, pid=%d)", args.ibus, os.getpid())

    cfg = cfg_mod.load()
    log.info("config: audio.device=%s stt.model_dir=%s",
             cfg.audio.device, cfg.stt.model_dir)

    # Inject shared state into engine class before any instance is created.
    VoiceEngine.stt = _load_stt(cfg)
    VoiceEngine.device = cfg.audio.device

    bus = IBus.Bus()
    if not bus.is_connected():
        log.error("Cannot connect to IBus daemon. Is `ibus-daemon` running?")
        return 2

    loop = GLib.MainLoop()

    def _on_disconnected(_bus):
        log.warning("disconnected from IBus daemon, quitting")
        loop.quit()

    bus.connect("disconnected", _on_disconnected)

    factory = IBus.Factory.new(bus.get_connection())
    factory.add_engine(ENGINE_NAME, VoiceEngine.__gtype__)

    # The daemon reaches into our process via this bus name — required in both
    # modes, even when daemon-launched from an XML component.
    bus.request_name(BUS_NAME, 0)

    if args.ibus:
        # Daemon spawned us because the XML told it about 'voice'; don't
        # re-register the component (would conflict with the static XML).
        log.info("provided engine factory for %s on bus %s (daemon-launched)",
                 ENGINE_NAME, BUS_NAME)
    else:
        # Standalone dev mode: register component dynamically so `ibus engine
        # voice` works without the XML being installed system-wide.
        component = _build_component()
        bus.register_component(component)
        log.info("registered component dynamically on bus %s (standalone mode)", BUS_NAME)

    try:
        loop.run()
    except KeyboardInterrupt:
        log.info("interrupted, exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
