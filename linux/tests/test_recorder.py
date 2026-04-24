"""Recorder tests — no live microphone needed.

We don't mock subprocess because arecord is a Pretty Small dependency; instead,
we test the pure-Python surface (state transitions, error paths) and one
lightweight integration that actually records ~0.5s and asserts the buffer
has sensible size / format.

Integration test is skipped if arecord isn't installed.
"""
from __future__ import annotations

import shutil
import time
import wave

import pytest

from voice_ibus import recorder as rec_mod
from voice_ibus.recorder import (
    CHANNELS,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    Recorder,
    RecorderError,
    pcm_to_wav,
)


def test_double_start_raises():
    r = Recorder()
    # Emulate an already-running state without actually launching arecord.
    r._proc = object()  # type: ignore[assignment]
    with pytest.raises(RecorderError):
        r.start()


def test_stop_without_start_raises():
    r = Recorder()
    with pytest.raises(RecorderError):
        r.stop()


def test_missing_pw_record_raises(monkeypatch):
    def fake_popen(*_a, **_kw):
        raise FileNotFoundError("pw-record")

    monkeypatch.setattr(rec_mod.subprocess, "Popen", fake_popen)
    r = Recorder()
    with pytest.raises(RecorderError, match="pw-record"):
        r.start()


def test_pcm_to_wav_roundtrip(tmp_path):
    pcm = b"\x00\x00" * (SAMPLE_RATE // 4)  # 0.25s of silence
    out = tmp_path / "x.wav"
    pcm_to_wav(pcm, out)
    with wave.open(str(out), "rb") as w:
        assert w.getnchannels() == CHANNELS
        assert w.getframerate() == SAMPLE_RATE
        assert w.getsampwidth() == SAMPLE_WIDTH
        assert w.readframes(w.getnframes()) == pcm


@pytest.mark.skipif(shutil.which("pw-record") is None, reason="pw-record not installed")
def test_live_capture_1s():
    r = Recorder()
    r.start()
    assert r.is_recording
    time.sleep(1.5)
    pcm = r.stop()
    assert not r.is_recording
    # pw-record has ~300-500 ms startup latency; be generous on the low side.
    one_sec_bytes = SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS
    assert 0.3 * one_sec_bytes <= len(pcm) <= 2.0 * one_sec_bytes, (
        f"got {len(pcm)} bytes, expected roughly {one_sec_bytes}"
    )
