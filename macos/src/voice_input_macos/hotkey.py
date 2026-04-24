"""Global hotkey push-to-talk controller for macOS.

Uses pynput (Quartz CGEvent taps). Requires Accessibility permission
(System Settings > Privacy & Security > Accessibility).

State machine:

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

from pynput import keyboard

from voice_input_macos.injector import InjectError, paste_text
from voice_input_macos.paths import LOG_DIR
from shared.audio import Recorder, RecorderError, pcm_rms, pcm_to_wav

log = logging.getLogger(__name__)

MIN_AUDIO_SECONDS = 0.2
SILENCE_RMS_THRESHOLD = 60.0
DEBUG_WAV_ON_FAILURE = LOG_DIR


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


StatusCallback = Callable[[str], None]

# Key name → pynput mapping
_PTT_KEY_MAP = {
    "caps_lock": keyboard.Key.caps_lock,
    "right_option": keyboard.Key.alt_r,
    "left_option": keyboard.Key.alt_l,
    "right_cmd": keyboard.Key.cmd_r,
    "left_cmd": keyboard.Key.cmd_l,
    "right_ctrl": keyboard.Key.ctrl_r,
    "left_ctrl": keyboard.Key.ctrl_l,
    "right_shift": keyboard.Key.shift_r,
    "left_shift": keyboard.Key.shift_l,
    **{f"f{n}": getattr(keyboard.Key, f"f{n}") for n in range(1, 21)
       if hasattr(keyboard.Key, f"f{n}")},
}


def _resolve_ptt_key(name: str):
    """Map a config key name to a pynput Key or KeyCode."""
    name_lower = name.lower().strip()
    if name_lower in _PTT_KEY_MAP:
        return _PTT_KEY_MAP[name_lower]
    # Single character → KeyCode
    if len(name_lower) == 1:
        return keyboard.KeyCode.from_char(name_lower)
    log.warning("unknown ptt key %r, falling back to caps_lock", name)
    return keyboard.Key.caps_lock


class HotkeyController:
    def __init__(
        self,
        ptt_key: str,
        recorder: Recorder,
        stt,
        *,
        inject_method: str = "paste",
        restore_clipboard: bool = True,
        paste_delay: float = 0.08,
        on_status: StatusCallback | None = None,
        on_state_change: Callable[[State], None] | None = None,
        on_text: Callable[[str], None] | None = None,
    ) -> None:
        self._ptt_key = _resolve_ptt_key(ptt_key)
        self._ptt_name = ptt_key
        self._recorder = recorder
        self._stt = stt
        self._inject_method = inject_method
        self._restore_clipboard = restore_clipboard
        self._paste_delay = paste_delay
        self._on_status = on_status or (lambda s: None)
        self._on_state_change = on_state_change or (lambda s: None)
        self._on_text = on_text or (lambda s: None)

        self._state = State.IDLE
        self._rec_started_at = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._listener: keyboard.Listener | None = None

    def _status(self, msg: str) -> None:
        log.info("status: %s", msg)
        try:
            self._on_status(msg)
        except Exception:
            log.exception("status callback failed")

    def _set_state(self, state: State) -> None:
        with self._lock:
            self._state = state
        try:
            self._on_state_change(state)
        except Exception:
            log.exception("state_change callback failed")

    @property
    def state(self) -> State:
        return self._state

    def start(self) -> None:
        """Register hotkey hooks without blocking."""
        log.info("registering hotkey: press-and-hold %s", self._ptt_name)
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        self._status(f"ready — hold [{self._ptt_name}] to speak")

    def run(self) -> None:
        """Register hotkey hooks and block until stop() is called."""
        self.start()
        try:
            self._stop_event.wait()
        finally:
            if self._listener is not None:
                self._listener.stop()

    def stop(self) -> None:
        self._stop_event.set()

    # --- event handlers (run on pynput's listener thread) ---

    def _on_press(self, key) -> None:
        if key != self._ptt_key:
            return
        with self._lock:
            if self._state is not State.IDLE:
                return
        try:
            self._recorder.start()
        except RecorderError as e:
            log.error("recorder start failed: %s", e)
            self._status(f"mic error: {e}")
            self._set_state(State.IDLE)
            return
        self._set_state(State.RECORDING)
        self._rec_started_at = time.monotonic()
        self._status("recording...")

    def _on_release(self, key) -> None:
        if key != self._ptt_key:
            return
        with self._lock:
            if self._state is not State.RECORDING:
                return
        self._set_state(State.PROCESSING)

        try:
            pcm = self._recorder.stop()
        except Exception as e:
            log.exception("recorder stop failed")
            self._status(f"stop failed: {e}")
            self._set_state(State.IDLE)
            return

        dur = time.monotonic() - self._rec_started_at
        log.info("captured %.2fs of audio (%d bytes)", dur, len(pcm))

        bytes_per_sec = 16_000 * 2
        if len(pcm) < bytes_per_sec * MIN_AUDIO_SECONDS:
            self._status("(too short)")
            self._set_state(State.IDLE)
            return

        rms = pcm_rms(pcm)
        if rms < SILENCE_RMS_THRESHOLD:
            self._status(f"(silent RMS={rms:.0f}, check mic)")
            self._set_state(State.IDLE)
            return

        threading.Thread(
            target=self._recognize_and_commit,
            args=(pcm, dur),
            daemon=True,
        ).start()

    def _recognize_and_commit(self, pcm: bytes, dur: float) -> None:
        self._status("recognizing...")
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
            self._status(f"STT error: {e}")
            self._set_state(State.IDLE)
            return

        if not text:
            self._status("(no speech)")
            self._set_state(State.IDLE)
            return

        try:
            paste_text(
                text,
                method=self._inject_method,
                restore_clipboard=self._restore_clipboard,
                paste_delay=self._paste_delay,
            )
        except InjectError as e:
            log.exception("injection failed")
            self._status(f"paste failed: {e}")
            self._set_state(State.IDLE)
            return

        preview = text if len(text) <= 30 else text[:30] + "..."
        self._status(f" {preview}")
        try:
            self._on_text(text)
        except Exception:
            log.exception("on_text callback failed")
        self._set_state(State.IDLE)
