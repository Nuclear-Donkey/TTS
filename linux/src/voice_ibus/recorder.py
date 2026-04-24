"""Microphone capture via `pw-record` (PipeWire native).

Why pw-record instead of arecord:
- arecord talks ALSA directly; on PipeWire-first systems the ALSA "default"
  PCM often resolves to the speaker-monitor source, not the actual mic
  (producing pure silence → ASR hallucinates).
- pw-record takes a PipeWire source name via --target and routes correctly.
- Zero extra pip dependencies.

Device config:
- "default" → auto-detect the first non-monitor capture source via `pactl`
- explicit PipeWire source name (e.g. "alsa_input.pci-0000_00_1f.3.analog-stereo")
- explicit node ID (numeric string)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import wave
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
_READ_CHUNK = 4096
MAX_SECONDS = 120


class RecorderError(RuntimeError):
    pass


def _resolve_device(device: str) -> Optional[str]:
    """Map a user-configured device string to a concrete pw-record --target value.

    Returns None for 'default' (let pw-record pick), or an explicit source name.
    If 'default' is given, attempts to auto-detect the first non-monitor source
    by asking pactl.
    """
    if device and device != "default":
        return device

    pactl = shutil.which("pactl")
    if pactl is None:
        return None  # no pactl → let pw-record use its own default

    try:
        out = subprocess.check_output(
            [pactl, "list", "short", "sources"],
            text=True,
            timeout=2,
        )
    except Exception:
        log.exception("pactl list sources failed; letting pw-record pick default")
        return None

    candidates = []
    for line in out.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[1]
        if name.endswith(".monitor"):
            continue  # speaker monitor, never what we want
        candidates.append(name)

    if not candidates:
        log.warning("no non-monitor source found via pactl; using pw-record default")
        return None

    log.info("auto-detected capture source: %s", candidates[0])
    return candidates[0]


class Recorder:
    def __init__(self, device: str = "default") -> None:
        self._device_cfg = device
        self._target: Optional[str] = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._wav_path: Path = Path()
        self._stop_flag = threading.Event()

    @property
    def is_recording(self) -> bool:
        return self._proc is not None

    def start(self) -> None:
        if self._proc is not None:
            raise RecorderError("already recording")
        self._stop_flag.clear()

        # Fresh tempfile per utterance so an earlier failure doesn't leak into
        # the next one.
        import tempfile
        self._wav_path = Path(tempfile.mktemp(prefix="voice-ibus-", suffix=".wav"))
        self._target = _resolve_device(self._device_cfg)

        cmd = [
            "pw-record",
            "--rate", str(SAMPLE_RATE),
            "--channels", str(CHANNELS),
            "--format", "s16",
            str(self._wav_path),
        ]
        if self._target:
            cmd.extend(["--target", self._target])
        log.debug("start: %s", " ".join(cmd))

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise RecorderError("pw-record not found; install pipewire-bin") from e

    def stop(self) -> bytes:
        if self._proc is None:
            raise RecorderError("not recording")
        self._stop_flag.set()
        proc = self._proc
        wav_path = self._wav_path
        self._proc = None
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                log.warning("pw-record did not exit in 2s, killing")
                proc.kill()
                proc.wait(timeout=1.0)
            if proc.stderr is not None:
                try:
                    err = proc.stderr.read()
                    if err:
                        log.debug("pw-record stderr: %s",
                                  err.decode("utf-8", "replace").strip())
                except Exception:
                    pass

            if not wav_path.exists():
                log.warning("pw-record produced no output file")
                return b""

            try:
                with wave.open(str(wav_path), "rb") as w:
                    if (w.getnchannels() != CHANNELS
                            or w.getsampwidth() != SAMPLE_WIDTH
                            or w.getframerate() != SAMPLE_RATE):
                        log.warning(
                            "unexpected wav format: ch=%d sw=%d rate=%d",
                            w.getnchannels(), w.getsampwidth(), w.getframerate(),
                        )
                    pcm = w.readframes(w.getnframes())
            except Exception:
                log.exception("reading wav %s failed", wav_path)
                pcm = b""
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

        log.info("captured %d bytes (%.2fs) target=%s",
                 len(pcm), len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
                 self._target or "pw-default")
        return pcm

    def cancel(self) -> None:
        if self._proc is None:
            return
        try:
            self.stop()
        except Exception:
            log.exception("cancel: stop failed")


def pcm_to_wav(pcm: bytes, path: str | Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)


def pcm_rms(pcm: bytes) -> float:
    """Root-mean-square amplitude of S16_LE mono PCM in [0, 32767]."""
    if not pcm:
        return 0.0
    import numpy as np
    a = np.frombuffer(pcm, dtype=np.int16)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))
