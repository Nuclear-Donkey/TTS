"""Global hotkey push-to-talk controller.

Uses the `keyboard` library (low-level Windows hook). Requires the
Python process to run as Administrator — keyboard hooks into high-level
input, and without admin privileges UAC-elevated applications (like
some game launchers, Task Manager, etc.) won't receive our hotkey.

State machine mirrors the Linux version but without IBus concerns:

    IDLE ─[PTT down]→ RECORDING ─[PTT up]→ PROCESSING ─[commit]→ IDLE
                         │
                         └─[error]→ IDLE
"""
from __future__ import annotations

import enum
import logging
import threading
import time
from pathlib import Path
from typing import Callable

import keyboard

from voice_input_win.injector import InjectError, paste_text
from voice_input_win.paths import LOG_DIR
from voice_input_win.recorder import Recorder, RecorderError, pcm_rms, pcm_to_wav

log = logging.getLogger(__name__)

MIN_AUDIO_SECONDS = 0.2
SILENCE_RMS_THRESHOLD = 60.0
DEBUG_WAV_ON_FAILURE = LOG_DIR


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


StatusCallback = Callable[[str], None]


class HotkeyController:
    def __init__(
        self,
        ptt_key: str,
        recorder: Recorder,
        stt,  # ParaformerStt, kept untyped to avoid circular import on stub
        *,
        restore_clipboard: bool = True,
        paste_delay: float = 0.05,
        on_status: StatusCallback | None = None,
        on_state_change: Callable[[State], None] | None = None,
        on_text: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._ptt_key = ptt_key.lower()
        self._recorder = recorder
        self._stt = stt
        self._restore_clipboard = restore_clipboard
        self._paste_delay = paste_delay
        self._on_status = on_status or (lambda s: None)
        self._on_state_change = on_state_change or (lambda s: None)
        self._on_text = on_text or (lambda s: None)
        self._on_error = on_error or (lambda s: None)

        self._state = State.IDLE
        self._rec_started_at = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def _status(self, msg: str) -> None:
        log.info("status: %s", msg)
        try:
            self._on_status(msg)
        except Exception:
            log.exception("status callback failed")

    def _emit_state(self, state: State) -> None:
        try:
            self._on_state_change(state)
        except Exception:
            log.exception("state_change callback failed")

    def _emit_error(self, msg: str) -> None:
        try:
            self._on_error(msg)
        except Exception:
            log.exception("error callback failed")

    def run(self) -> None:
        """Register hotkey hooks and block until stop() is called."""
        log.info("registering hotkey: press-and-hold %s", self._ptt_key)
        try:
            keyboard.on_press_key(self._ptt_key, self._on_press, suppress=False)
            keyboard.on_release_key(self._ptt_key, self._on_release, suppress=False)
        except Exception as e:
            raise RuntimeError(
                f"could not register hotkey {self._ptt_key!r}. "
                f"Are you running as Administrator? ({e})"
            ) from e

        self._status(f"ready — hold [{self._ptt_key}] to speak")
        try:
            self._stop_event.wait()
        finally:
            keyboard.unhook_all()

    def stop(self) -> None:
        self._stop_event.set()

    # --- event handlers (run on keyboard lib's listener thread) -------

    def _on_press(self, _evt) -> None:
        with self._lock:
            if self._state is not State.IDLE:
                return
            self._state = State.RECORDING
        try:
            self._recorder.start()
        except RecorderError as e:
            log.error("recorder start failed: %s", e)
            self._status(f"✗ mic error: {e}")
            self._emit_error(f"mic error: {e}")
            with self._lock:
                self._state = State.IDLE
            self._emit_state(State.IDLE)
            return
        self._rec_started_at = time.monotonic()
        self._status("● recording…")
        self._emit_state(State.RECORDING)

    def _on_release(self, _evt) -> None:
        with self._lock:
            if self._state is not State.RECORDING:
                return
            self._state = State.PROCESSING
        self._emit_state(State.PROCESSING)

        try:
            pcm = self._recorder.stop()
        except Exception as e:
            log.exception("recorder stop failed")
            self._status(f"✗ stop failed: {e}")
            self._emit_error(f"stop failed: {e}")
            with self._lock:
                self._state = State.IDLE
            self._emit_state(State.IDLE)
            return

        dur = time.monotonic() - self._rec_started_at
        log.info("captured %.2fs of audio (%d bytes)", dur, len(pcm))

        bytes_per_sec = 16_000 * 2
        if len(pcm) < bytes_per_sec * MIN_AUDIO_SECONDS:
            self._status("(too short)")
            self._emit_error("录音过短")
            with self._lock:
                self._state = State.IDLE
            self._emit_state(State.IDLE)
            return

        rms = pcm_rms(pcm)
        if rms < SILENCE_RMS_THRESHOLD:
            self._status(f"(silent RMS={rms:.0f}, check mic)")
            self._emit_error(f"麦克风静音 (RMS={rms:.0f})")
            with self._lock:
                self._state = State.IDLE
            self._emit_state(State.IDLE)
            return

        # STT in a worker thread so the listener thread stays responsive
        # (keyboard lib dispatches on a background thread already, but we
        # want to return from this handler fast so follow-up events aren't
        # queued behind a 100ms decode).
        threading.Thread(
            target=self._recognize_and_commit,
            args=(pcm, dur),
            daemon=True,
        ).start()

    def _recognize_and_commit(self, pcm: bytes, dur: float) -> None:
        self._status("⏳ recognizing…")
        try:
            text = self._stt.recognize(pcm)
        except Exception as e:
            log.exception("STT failed")
            try:
                DEBUG_WAV_ON_FAILURE.mkdir(parents=True, exist_ok=True)
                fail_path = DEBUG_WAV_ON_FAILURE / f"voice-failed-{int(time.time())}.wav"
                pcm_to_wav(pcm, fail_path)
                log.info("dumped failed audio to %s", fail_path)
            except Exception:
                log.exception("failed to dump audio")
            self._status(f"✗ STT error: {e}")
            self._emit_error(f"STT 错误: {e}")
            with self._lock:
                self._state = State.IDLE
            self._emit_state(State.IDLE)
            return

        if not text:
            self._status("(no speech)")
            self._emit_error("未检测到语音")
            with self._lock:
                self._state = State.IDLE
            self._emit_state(State.IDLE)
            return

        try:
            paste_text(
                text,
                restore_clipboard=self._restore_clipboard,
                paste_delay=self._paste_delay,
            )
        except InjectError as e:
            log.exception("injection failed")
            self._status(f"✗ paste failed: {e}")
            self._emit_error(f"粘贴失败: {e}")
            with self._lock:
                self._state = State.IDLE
            self._emit_state(State.IDLE)
            return

        preview = text if len(text) <= 30 else text[:30] + "…"
        self._status(f"✓ {preview}")
        try:
            self._on_text(text)
        except Exception:
            log.exception("on_text callback failed")
        with self._lock:
            self._state = State.IDLE
        self._emit_state(State.IDLE)
