"""Download Paraformer-zh model to %LOCALAPPDATA%\\voice-input\\models\\paraformer-zh\\.

Same logic as the Linux version but uses Windows paths. Idempotent.
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

DEFAULT_DEST = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) \
    / "voice-input" / "models" / "paraformer-zh"

MODELS = {
    "full": {
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-2024-03-09.tar.bz2",
        "size_mb": 230,
    },
    "small": {
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-small-2024-03-09.tar.bz2",
        "size_mb": 79,
    },
}


def _download(url: str, dest_file: Path) -> None:
    print(f"Downloading {url}")
    print(f"       -> {dest_file}")
    req = urllib.request.Request(url, headers={"User-Agent": "voice-input-win/0.1"})
    with urllib.request.urlopen(req) as resp:
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
        for member in tf.getmembers():
            name = Path(member.name)
            if len(name.parts) < 2:
                continue
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
                   help="download 79MB small model instead of 217MB full")
    p.add_argument("--url", default=None, help="override URL (for mirror)")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    info = MODELS["small" if args.small else "full"]
    url = args.url or info["url"]
    primary = args.dest / "model.int8.onnx"
    tokens = args.dest / "tokens.txt"

    if primary.exists() and tokens.exists() and not args.force:
        print(f"Model already present: {primary}")
        print("(pass --force to redownload)")
        return 0

    args.dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="voice-input-dl-") as tmpdir:
        tarball = Path(tmpdir) / "model.tar.bz2"
        try:
            _download(url, tarball)
        except Exception as e:
            print(f"Download failed: {e}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Try a mirror via --url, or download the .tar.bz2 manually and extract to:",
                  file=sys.stderr)
            print(f"  {args.dest}", file=sys.stderr)
            return 1
        _extract(tarball, args.dest)

    if not (primary.exists() and tokens.exists()):
        print("ERROR: archive did not contain expected files", file=sys.stderr)
        return 2

    print()
    print(f"OK: model installed under {args.dest}")
    print(f"     weights: {primary}")
    print(f"     tokens:  {tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
