"""Sherpa-ONNX Paraformer wrapper.

Loads the offline recognizer once at construction and reuses it for every
utterance. Input: 16kHz mono S16_LE PCM bytes. Output: recognized text.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import sherpa_onnx

log = logging.getLogger(__name__)


class SttError(RuntimeError):
    pass


class ParaformerStt:
    """Blocking offline recognizer. Thread-safe for serial use (one utterance
    at a time); not safe for concurrent recognize() from multiple threads."""

    def __init__(self, model_dir: str | Path, num_threads: int = 4) -> None:
        model_dir = Path(model_dir).expanduser()
        model_path = model_dir / "model.int8.onnx"
        if not model_path.exists():
            # fall back to non-quantized if user downloaded the full model
            model_path = model_dir / "model.onnx"
        tokens_path = model_dir / "tokens.txt"

        if not model_path.exists() or not tokens_path.exists():
            raise SttError(
                f"Paraformer model not found under {model_dir}. "
                f"Run scripts/download-model.py first."
            )

        log.info("loading Paraformer from %s (threads=%d)", model_path, num_threads)
        t0 = time.monotonic()
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=str(model_path),
            tokens=str(tokens_path),
            num_threads=num_threads,
            sample_rate=16_000,
            feature_dim=80,
            decoding_method="greedy_search",
            provider="cpu",
        )
        log.info("Paraformer loaded in %.2fs", time.monotonic() - t0)

        # Warm up so the first real call isn't cold-penalty slow.
        self._warmup()

    def _warmup(self) -> None:
        silent = np.zeros(16_000, dtype=np.float32)  # 1s silence
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16_000, silent)
        self._recognizer.decode_stream(stream)
        log.debug("warmup decode done")

    def recognize(self, pcm_s16_le: bytes) -> str:
        """Decode PCM bytes (S16_LE mono 16kHz) → text. Returns "" on empty input."""
        if not pcm_s16_le:
            return ""
        # int16 → float32 in [-1, 1]
        audio = np.frombuffer(pcm_s16_le, dtype=np.int16).astype(np.float32) / 32768.0

        t0 = time.monotonic()
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16_000, audio)
        self._recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        log.info(
            "recognize: %.2fs audio → '%s' in %.2fs (RTF %.2f)",
            len(audio) / 16_000,
            text,
            time.monotonic() - t0,
            (time.monotonic() - t0) / max(len(audio) / 16_000, 1e-6),
        )
        return text


# CLI: `python -m voice_ibus.stt path/to.wav` for manual verification.
def _cli() -> int:
    import argparse
    import wave

    p = argparse.ArgumentParser()
    p.add_argument("wav")
    p.add_argument("--model-dir", default="~/.local/share/ibus-voice/models/paraformer-zh")
    p.add_argument("--threads", type=int, default=4)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    with wave.open(args.wav, "rb") as w:
        assert w.getnchannels() == 1, "expected mono"
        assert w.getsampwidth() == 2, "expected 16-bit"
        assert w.getframerate() == 16_000, "expected 16kHz"
        pcm = w.readframes(w.getnframes())

    stt = ParaformerStt(args.model_dir, num_threads=args.threads)
    print(stt.recognize(pcm))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
