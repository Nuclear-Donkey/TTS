"""First-run experience: download model (with progress dialog) and
create desktop / start-menu shortcuts.

All routines here are safe to call repeatedly — they only act when needed.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QProgressDialog, QMessageBox

from voice_input_win.model_downloader import (
    download_and_extract,
    is_model_present,
)

log = logging.getLogger(__name__)


# ── model download ─────────────────────────────────────────────────

class _DownloadWorker(QObject):
    progress = pyqtSignal(int, int)   # got, total
    finished = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, dest: Path, variant: str = "small") -> None:
        super().__init__()
        self._dest = dest
        self._variant = variant

    def run(self) -> None:
        try:
            download_and_extract(
                self._dest,
                variant=self._variant,
                progress=lambda g, t: self.progress.emit(g, t),
            )
            self.finished.emit()
        except Exception as e:
            log.exception("model download failed")
            self.failed.emit(str(e))


def ensure_model(dest: Path, *, variant: str = "small") -> bool:
    """Blocking (Qt-modal) model ensure. Returns True on success."""
    if is_model_present(dest):
        return True

    dlg = QProgressDialog("正在下载识别模型...", "取消", 0, 100)
    dlg.setWindowTitle("voice-input — 首次启动")
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setMinimumDuration(0)
    dlg.setValue(0)

    thread = QThread()
    worker = _DownloadWorker(dest, variant=variant)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    result = {"ok": False, "err": ""}

    def _on_progress(got: int, total: int) -> None:
        if total > 0:
            dlg.setValue(int(got * 100 / total))
            dlg.setLabelText(
                f"正在下载识别模型... {got/1e6:.1f} / {total/1e6:.1f} MB"
            )
        else:
            dlg.setLabelText(f"正在下载识别模型... {got/1e6:.1f} MB")

    def _on_done() -> None:
        result["ok"] = True
        dlg.setValue(100)
        dlg.close()
        thread.quit()

    def _on_fail(msg: str) -> None:
        result["err"] = msg
        dlg.close()
        thread.quit()

    worker.progress.connect(_on_progress)
    worker.finished.connect(_on_done)
    worker.failed.connect(_on_fail)

    thread.start()
    dlg.exec()

    # If user cancelled
    if dlg.wasCanceled() and not result["ok"]:
        thread.requestInterruption()
        thread.quit()
        thread.wait(2000)
        return False

    thread.wait(5000)

    if not result["ok"]:
        QMessageBox.critical(
            None, "voice-input",
            f"模型下载失败：\n{result['err']}\n\n"
            f"请检查网络后重启程序，或手动把 Paraformer-zh 模型放到：\n{dest}"
        )
        return False
    return True


# ── shortcut creation ──────────────────────────────────────────────

def create_desktop_shortcut(target_exe: Path) -> None:
    """Create a .lnk on the desktop pointing at voice-input.exe.

    No-op on non-Windows, or if the shortcut already exists.
    """
    if os.name != "nt":
        return
    try:
        desktop = _desktop_dir()
        if desktop is None:
            return
        link = desktop / "voice-input.lnk"
        if link.exists():
            return
        _make_shortcut(link, target_exe)
        log.info("created desktop shortcut: %s", link)
    except Exception:
        log.exception("create_desktop_shortcut failed (non-fatal)")


def create_start_menu_shortcut(target_exe: Path) -> None:
    if os.name != "nt":
        return
    try:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return
        programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        link = programs / "voice-input.lnk"
        if link.exists():
            return
        programs.mkdir(parents=True, exist_ok=True)
        _make_shortcut(link, target_exe)
        log.info("created start menu shortcut: %s", link)
    except Exception:
        log.exception("create_start_menu_shortcut failed (non-fatal)")


def _desktop_dir() -> Path | None:
    userprofile = os.environ.get("USERPROFILE")
    if not userprofile:
        return None
    return Path(userprofile) / "Desktop"


def _make_shortcut(link: Path, target: Path) -> None:
    """Create a .lnk via WSH (comes with Windows, no extra deps)."""
    # Use pythoncom + win32com if available, else fall back to PowerShell
    try:
        import pythoncom  # type: ignore[import-not-found]
        from win32com.client import Dispatch  # type: ignore[import-not-found]
        pythoncom.CoInitialize()
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(link))
        shortcut.Targetpath = str(target)
        shortcut.WorkingDirectory = str(target.parent)
        shortcut.IconLocation = str(target)
        shortcut.save()
        return
    except ImportError:
        pass

    # Fallback: powershell
    import subprocess
    ps = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
        f"$s.TargetPath='{target}';"
        f"$s.WorkingDirectory='{target.parent}';"
        f"$s.IconLocation='{target}';"
        f"$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=True, capture_output=True,
    )


# ── entry point used by __main__ ────────────────────────────────────

def run_if_needed(model_dir: Path) -> bool:
    """Do everything a first launch might need. Returns True if we can
    proceed to the main event loop, False if the user should be blocked.
    """
    if not ensure_model(model_dir):
        return False

    # Shortcuts only after packaging (sys.frozen) — skip in dev mode so we
    # don't litter the user's desktop during development.
    if getattr(sys, "frozen", False):
        try:
            exe = Path(sys.executable)
            create_desktop_shortcut(exe)
            create_start_menu_shortcut(exe)
        except Exception:
            log.exception("shortcut creation failed (non-fatal)")

    return True
