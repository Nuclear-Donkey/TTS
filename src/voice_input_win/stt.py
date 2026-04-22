"""Paraformer STT wrapper — shared logic with Linux version.

Cross-platform: sherpa-onnx has identical Python API on Windows/Linux/Mac.
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
    def __init__(self, model_dir: str | Path, num_threads: int = 4) -> None:
        model_dir = Path(model_dir).expanduser()
        model_path = model_dir / "model.int8.onnx"
        if not model_path.exists():
            model_path = model_dir / "model.onnx"
        tokens_path = model_dir / "tokens.txt"

        if not model_path.exists() or not tokens_path.exists():
            raise SttError(
                f"Paraformer model not found under {model_dir}. "
                f"Run scripts\\download_model.py first."
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
        self._warmup()

    def _warmup(self) -> None:
        silent = np.zeros(16_000, dtype=np.float32)
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16_000, silent)
        self._recognizer.decode_stream(stream)
        log.debug("warmup decode done")

    def recognize(self, pcm_s16_le: bytes) -> str:
        if not pcm_s16_le:
            return ""
        audio = np.frombuffer(pcm_s16_le, dtype=np.int16).astype(np.float32) / 32768.0
        t0 = time.monotonic()
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16_000, audio)
        self._recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        log.info(
            "recognize: %.2fs audio → %r in %.2fs (RTF %.2f)",
            len(audio) / 16_000,
            text,
            time.monotonic() - t0,
            (time.monotonic() - t0) / max(len(audio) / 16_000, 1e-6),
        )
        return text
