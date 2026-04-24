"""Paraformer model downloader — importable (for Qt UI) and CLI-callable.

Progress callback is `fn(got_bytes, total_bytes)`. Raises on failure.
"""
from __future__ import annotations

import logging
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

URLS = {
    "small": (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
        "sherpa-onnx-paraformer-zh-small-2024-03-09.tar.bz2"
    ),
    "full": (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
        "sherpa-onnx-paraformer-zh-2024-03-09.tar.bz2"
    ),
}

ProgressCb = Callable[[int, int], None]


def is_model_present(dest: Path) -> bool:
    return (dest / "tokens.txt").exists() and any(dest.glob("*.onnx"))


def download_and_extract(
    dest: Path,
    *,
    variant: str = "small",
    url: str | None = None,
    progress: ProgressCb | None = None,
) -> None:
    """Download `variant` model and extract into `dest`."""
    target_url = url or URLS[variant]
    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="voice-input-dl-") as tmp:
        tarball = Path(tmp) / "model.tar.bz2"
        _download(target_url, tarball, progress=progress)
        _extract(tarball, dest)

    if not is_model_present(dest):
        raise RuntimeError(
            f"archive extracted but expected files missing in {dest}"
        )


def _download(url: str, out: Path, *, progress: ProgressCb | None) -> None:
    log.info("downloading %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "voice-input-win/0.2"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        got = 0
        chunk = 1024 * 256
        with out.open("wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                got += len(buf)
                if progress is not None:
                    try:
                        progress(got, total)
                    except Exception:
                        log.debug("progress cb failed", exc_info=True)


def _extract(tarball: Path, dest: Path) -> None:
    log.info("extracting to %s", dest)
    with tarfile.open(tarball, "r:bz2") as tf:
        for member in tf.getmembers():
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            rel = Path(*parts[1:])
            if member.isdir():
                (dest / rel).mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                tgt = dest / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(member) as src, tgt.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
