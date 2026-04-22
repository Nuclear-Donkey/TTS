#!/usr/bin/env python3
"""Download Paraformer-zh model for voice-ibus.

Downloads and extracts the sherpa-onnx Paraformer Chinese model to
~/.local/share/ibus-voice/models/paraformer-zh/. Idempotent — skips if the
model files are already present.

Usage:
    python scripts/download-model.py
    python scripts/download-model.py --url https://your-mirror/file.tar.bz2
    python scripts/download-model.py --small   # smaller 79MB int8 model
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

DEFAULT_DEST = Path.home() / ".local/share/ibus-voice/models/paraformer-zh"

MODELS = {
    "full": {
        "name": "sherpa-onnx-paraformer-zh-2024-03-09",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-2024-03-09.tar.bz2",
        "size_mb": 230,
        "primary_weight": "model.int8.onnx",
    },
    "small": {
        "name": "sherpa-onnx-paraformer-zh-small-2024-03-09",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-small-2024-03-09.tar.bz2",
        "size_mb": 79,
        "primary_weight": "model.int8.onnx",
    },
}


def _download(url: str, dest_file: Path) -> None:
    print(f"Downloading {url}")
    print(f"       → {dest_file}")
    with urllib.request.urlopen(url) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        got = 0
        chunk = 1024 * 256
        h = hashlib.sha256()
        with dest_file.open("wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                h.update(buf)
                got += len(buf)
                if total:
                    pct = got * 100 / total
                    print(f"  {got/1e6:7.1f} / {total/1e6:.1f} MB  ({pct:5.1f}%)", end="\r")
        print()
        print(f"  sha256: {h.hexdigest()}")


def _extract(tarball: Path, dest: Path) -> None:
    print(f"Extracting to {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:bz2") as tf:
        # Strip the top-level directory, place model.*.onnx and tokens.txt
        # directly under dest/
        for member in tf.getmembers():
            name = Path(member.name)
            if len(name.parts) < 2:
                continue
            # Skip the top directory component, keep the rest.
            rel = Path(*name.parts[1:])
            if member.isdir():
                (dest / rel).mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    p.add_argument("--small", action="store_true",
                   help="Use smaller 79MB int8 model instead of the 217MB int8")
    p.add_argument("--url", default=None,
                   help="Override download URL (useful for mirrors)")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    choice = "small" if args.small else "full"
    info = MODELS[choice]
    url = args.url or info["url"]
    expected = args.dest / info["primary_weight"]
    tokens = args.dest / "tokens.txt"

    if expected.exists() and tokens.exists() and not args.force:
        print(f"Model already present: {expected}")
        print(f"                       {tokens}")
        print("(pass --force to redownload)")
        return 0

    args.dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="voice-ibus-dl-") as tmpdir:
        tarball = Path(tmpdir) / "model.tar.bz2"
        try:
            _download(url, tarball)
        except Exception as e:
            print(f"Download failed: {e}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Try a mirror with --url, e.g. a ModelScope/HuggingFace mirror,", file=sys.stderr)
            print("or download the .tar.bz2 manually and extract to:", file=sys.stderr)
            print(f"  {args.dest}", file=sys.stderr)
            return 1
        _extract(tarball, args.dest)

    ok = expected.exists() and tokens.exists()
    if not ok:
        print("ERROR: extracted archive did not contain expected files", file=sys.stderr)
        print(f"  looking for: {expected}", file=sys.stderr)
        print(f"               {tokens}", file=sys.stderr)
        return 2

    print()
    print(f"✓ Model installed under {args.dest}")
    print(f"  primary weights: {expected}")
    print(f"  tokens:          {tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
