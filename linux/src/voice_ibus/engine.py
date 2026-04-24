"""IBus engine: PTT state machine → Recorder → STT (in worker thread) → commit_text.

STT runs in a background thread to keep the IBus / GLib main loop responsive;
its result returns to the main thread via GLib.idle_add before being committed
(IBus API calls must happen on the main thread).
"""
from __future__ import annotations

import enum
import logging
import threading
import time
from pathlib import Path

import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus

from voice_ibus.recorder import Recorder, RecorderError, pcm_rms, pcm_to_wav

log = logging.getLogger(__name__)

PTT_KEYVAL = IBus.KEY_Caps_Lock
CANCEL_KEYVAL = IBus.KEY_Escape
DEBUG_WAV_ON_FAILURE = Path("/tmp")  # wav dumped here on STT error
MIN_AUDIO_SECONDS = 0.2
# RMS threshold below which we treat the capture as silence and don't run STT.
# int16 range is 0-32767; typical ambient room noise is ~50-200, soft speech
# starts ~400+. 60 catches "mic is routed to monitor / muted" and doesn't
# needlessly invoke Paraformer which hallucinates on pure silence.
SILENCE_RMS_THRESHOLD = 60.0


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"


class VoiceEngine(IBus.Engine):
    __gtype_name__ = "VoiceEngine"

    # Class-level shared STT + config; set by the factory before the first
    # engine instance is created. Each per-focus engine instance reuses them.
    stt = None       # type: ignore[var-annotated]
    device = "default"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = State.IDLE
        self._recorder = Recorder(device=self.device)
        self._rec_started_at = 0.0
        log.info("VoiceEngine instantiated (stt=%s)", "ready" if self.stt else "missing")

    # --- IBus lifecycle -------------------------------------------------

    def do_focus_in(self):
        log.debug("focus_in")
        if self.stt is None:
            self._show_aux("✗ STT 未加载，看日志")
        else:
            self._show_aux("🎤 按住 CapsLock 说话")

    def do_focus_out(self):
        log.debug("focus_out")
        if self._state is State.RECORDING:
            log.info("focus_out during recording, cancelling")
            self._recorder.cancel()
            self._state = State.IDLE
        self._hide_aux()

    def do_enable(self):
        log.info("engine enabled")

    def do_disable(self):
        log.info("engine disabled")
        if self._state is State.RECORDING:
            self._recorder.cancel()
            self._state = State.IDLE

    # --- key handling ---------------------------------------------------

    def do_process_key_event(self, keyval: int, keycode: int, state: int) -> bool:
        is_release = bool(state & IBus.ModifierType.RELEASE_MASK)

        if keyval == PTT_KEYVAL:
            return self._handle_ptt(is_release)

        if keyval == CANCEL_KEYVAL and not is_release:
            if self._state is State.RECORDING:
                log.info("Escape: cancel recording")
                self._recorder.cancel()
                self._state = State.IDLE
                self._show_aux("✗ 已取消")
                GLib.timeout_add(800, self._reset_aux_to_idle)
                return True

        return False

    def _handle_ptt(self, is_release: bool) -> bool:
        if not is_release:
            if self._state is State.IDLE:
                self._start_recording()
            else:
                log.debug("PTT press ignored in state %s", self._state)
            return True  # swallow — prevent CapsLock modifier toggle

        # release
        if self._state is State.RECORDING:
            self._stop_recording_and_recognize()
        else:
            log.debug("PTT release ignored in state %s", self._state)
        return True  # swallow

    # --- recording + STT dispatch --------------------------------------

    def _start_recording(self) -> None:
        if self.stt is None:
            self._show_aux("✗ STT 未加载")
            GLib.timeout_add(1200, self._reset_aux_to_idle)
            return
        try:
            self._recorder.start()
        except RecorderError as e:
            log.error("recorder start failed: %s", e)
            self._state = State.ERROR
            self._show_aux(f"✗ 无麦克风: {e}")
            GLib.timeout_add(1500, self._reset_aux_to_idle)
            return
        self._state = State.RECORDING
        self._rec_started_at = time.monotonic()
        self._show_aux("● 录音中… 松开结束")

    def _stop_recording_and_recognize(self) -> None:
        self._state = State.PROCESSING
        self._show_aux("⏳ 识别中…")
        try:
            pcm = self._recorder.stop()
        except Exception as e:
            log.exception("recorder stop failed")
            self._state = State.ERROR
            self._show_aux(f"✗ 录音失败: {e}")
            GLib.timeout_add(1500, self._reset_aux_to_idle)
            return

        dur = time.monotonic() - self._rec_started_at
        bytes_per_sec = 16_000 * 2
        log.info("captured %.2fs of audio (%d bytes)", dur, len(pcm))

        if len(pcm) < bytes_per_sec * MIN_AUDIO_SECONDS:
            log.info("too short (%.2fs), ignoring", dur)
            self._state = State.IDLE
            self._show_aux("（太短）")
            GLib.timeout_add(700, self._reset_aux_to_idle)
            return

        rms = pcm_rms(pcm)
        if rms < SILENCE_RMS_THRESHOLD:
            log.info("silent capture (RMS=%.1f < %.1f), not running STT "
                     "(mic muted / routed to wrong source?)",
                     rms, SILENCE_RMS_THRESHOLD)
            self._state = State.IDLE
            self._show_aux(f"（静音 RMS={rms:.0f}，检查麦克风）")
            GLib.timeout_add(1500, self._reset_aux_to_idle)
            return

        # Off main-thread STT; callback commits on the main thread.
        worker = threading.Thread(
            target=self._recognize_worker,
            args=(pcm, dur),
            daemon=True,
        )
        worker.start()

    def _recognize_worker(self, pcm: bytes, dur: float) -> None:
        """Runs in a background thread. Must not touch IBus API directly."""
        try:
            text = self.stt.recognize(pcm)
            GLib.idle_add(self._on_recognize_done, text, dur)
        except Exception as e:
            log.exception("STT failed")
            try:
                fail_path = DEBUG_WAV_ON_FAILURE / f"voice-ibus-failed-{int(time.time())}.wav"
                pcm_to_wav(pcm, fail_path)
                log.info("dumped failed audio to %s", fail_path)
            except Exception:
                log.exception("failed to dump audio")
            GLib.idle_add(self._on_recognize_failed, str(e))

    # --- main-thread callbacks from STT thread -------------------------

    def _on_recognize_done(self, text: str, dur: float) -> bool:
        text = text.strip()
        log.info("recognized (%.2fs audio): %r", dur, text)
        if not text:
            self._state = State.IDLE
            self._show_aux("（无语音）")
            GLib.timeout_add(800, self._reset_aux_to_idle)
            return False

        try:
            self.commit_text(IBus.Text.new_from_string(text))
        except Exception:
            log.exception("commit_text failed")
            self._show_aux("✗ 上屏失败")
            GLib.timeout_add(1500, self._reset_aux_to_idle)
            self._state = State.ERROR
            return False

        self._state = State.IDLE
        # Brief "✓" flash, then back to idle message.
        self._show_aux(f"✓ {text[:20]}{'…' if len(text) > 20 else ''}")
        GLib.timeout_add(1000, self._reset_aux_to_idle)
        return False  # one-shot

    def _on_recognize_failed(self, err: str) -> bool:
        self._state = State.ERROR
        self._show_aux(f"✗ 识别失败: {err[:30]}")
        GLib.timeout_add(2000, self._reset_aux_to_idle)
        return False

    # --- aux helpers ----------------------------------------------------

    def _show_aux(self, text: str) -> None:
        t = IBus.Text.new_from_string(text)
        self.update_auxiliary_text(t, True)

    def _hide_aux(self) -> None:
        t = IBus.Text.new_from_string("")
        self.update_auxiliary_text(t, False)

    def _reset_aux_to_idle(self) -> bool:
        if self._state is State.ERROR:
            self._state = State.IDLE
        if self._state is State.IDLE:
            self._show_aux("🎤 按住 CapsLock 说话")
        return False  # one-shot
