"""Microphone capture via sounddevice (PortAudio) — cross-platform.

Push-to-talk style: start() begins streaming into an internal buffer,
stop() returns the accumulated S16_LE mono 16kHz PCM.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
MAX_SECONDS = 120

try:
    import sounddevice as sd
except OSError as e:  # PortAudio not found
    sd = None  # type: ignore[assignment]
    _import_error = str(e)
else:
    _import_error = ""


class RecorderError(RuntimeError):
    pass


def _resolve_device(device: str) -> Optional[int | str]:
    """Map config 'audio.device' to a sounddevice device identifier.

    - "" / "default" → None (sounddevice picks the system default input)
    - digit string → int (device index)
    - otherwise → substring match against device names (first match wins)
    """
    if not device or device.lower() == "default":
        return None
    if device.isdigit():
        return int(device)
    # Fuzzy match by substring
    if sd is None:
        return None
    device_lc = device.lower()
    for i, info in enumerate(sd.query_devices()):
        if info.get("max_input_channels", 0) > 0 and device_lc in info["name"].lower():
            log.info("matched audio device %d: %s", i, info["name"])
            return i
    log.warning("no audio device matching %r, falling back to default", device)
    return None


def list_input_devices() -> list[dict]:
    """Return [{"index": int, "name": str, "is_default": bool}, ...] for all input-capable devices."""
    if sd is None:
        return []
    default_in = None
    try:
        default_in = sd.default.device[0]
    except Exception:
        pass
    devices = []
    for i, info in enumerate(sd.query_devices()):
        if info.get("max_input_channels", 0) > 0:
            devices.append({
                "index": i,
                "name": info["name"],
                "is_default": (i == default_in),
            })
    return devices


class Recorder:
    def __init__(self, device: str = "") -> None:
        if sd is None:
            raise RecorderError(
                f"sounddevice import failed (PortAudio missing): {_import_error}"
            )
        self._device_cfg = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: Optional["sd.InputStream"] = None

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def device_cfg(self) -> str:
        return self._device_cfg

    @device_cfg.setter
    def device_cfg(self, value: str) -> None:
        self._device_cfg = value

    def start(self) -> None:
        if self._stream is not None:
            raise RecorderError("already recording")
        # Drain any leftover chunks from a prior aborted session.
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        def _cb(indata, frames, time_info, status):
            if status:
                log.debug("sd status: %s", status)
            self._queue.put(indata.copy())

        device_id = _resolve_device(self._device_cfg)
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=0,
                device=device_id,
                callback=_cb,
            )
            self._stream.start()
        except Exception as e:
            self._stream = None
            raise RecorderError(f"could not open audio device: {e}") from e
        log.debug("recording started (device=%s)", device_id)

    def stop(self) -> bytes:
        if self._stream is None:
            raise RecorderError("not recording")
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            log.exception("stream.close failed")
        finally:
            self._stream = None

        chunks: list[np.ndarray] = []
        total_samples = 0
        max_samples = MAX_SECONDS * SAMPLE_RATE * CHANNELS
        while not self._queue.empty():
            try:
                c = self._queue.get_nowait()
            except queue.Empty:
                break
            chunks.append(c)
            total_samples += c.size
            if total_samples >= max_samples:
                log.warning("hit %d-sample cap, truncating", max_samples)
                break

        if not chunks:
            return b""

        arr = np.concatenate(chunks, axis=0).flatten().astype(np.int16)
        pcm = arr.tobytes()
        log.info(
            "captured %d bytes (%.2fs)",
            len(pcm),
            len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
        )
        return pcm

    def cancel(self) -> None:
        if self._stream is None:
            return
        try:
            self.stop()
        except Exception:
            log.exception("cancel: stop failed")


def pcm_rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    a = np.frombuffer(pcm, dtype=np.int16)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))


def pcm_to_wav(pcm: bytes, path) -> None:
    import wave

    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
