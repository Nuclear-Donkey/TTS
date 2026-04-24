"""STT tests — require the model to be downloaded.

Skipped automatically when the model isn't present, so CI without model data
still passes.
"""
from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest

from voice_ibus.stt import ParaformerStt, SttError

MODEL_DIR = Path(os.path.expanduser("~/.local/share/ibus-voice/models/paraformer-zh"))
MODEL_AVAILABLE = (
    (MODEL_DIR / "model.int8.onnx").exists() and (MODEL_DIR / "tokens.txt").exists()
)


def test_raises_when_model_missing(tmp_path):
    with pytest.raises(SttError, match="not found"):
        ParaformerStt(tmp_path)


@pytest.mark.skipif(not MODEL_AVAILABLE, reason="model not downloaded")
def test_silence_returns_short_or_empty():
    # 1 second of silence shouldn't produce a long transcript.
    stt = ParaformerStt(MODEL_DIR, num_threads=2)
    silent_pcm = b"\x00\x00" * 16_000  # 1s @ 16kHz s16
    result = stt.recognize(silent_pcm)
    # Paraformer sometimes emits stray filler on silence; just require short.
    assert len(result) < 20, f"silence got unexpectedly long transcript: {result!r}"


@pytest.mark.skipif(not MODEL_AVAILABLE, reason="model not downloaded")
def test_empty_input_returns_empty():
    stt = ParaformerStt(MODEL_DIR, num_threads=2)
    assert stt.recognize(b"") == ""
