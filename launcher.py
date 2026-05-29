"""Tiny launcher that delegates to meeting_app.py via the local venv's pythonw.

Compiled with PyInstaller into NoteNara.exe so the user gets a real .exe with
the NoteNara icon embedded. The launcher itself ships <10 MB; the actual app
runtime (Python interpreter + libs) stays in venv/ next to it.

Critical detail: we set the same AppUserModelID that meeting_app.py uses BEFORE
spawning pythonw. Without this, Windows briefly groups the spawned pythonw
under its own (default) AppID and pins the Python feather icon to the taskbar
slot — even though meeting_app.py overrides the AppID shortly after, the
taskbar pin has already been decided.
"""
from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

APP_ID = "com.notenara.app.v2"


def _set_app_id() -> None:
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass


def _show_error(title: str, msg: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)  # MB_ICONERROR
    except Exception:
        print(f"{title}: {msg}", file=sys.stderr)


def main() -> int:
    _set_app_id()

    if getattr(sys, "frozen", False):
        here = Path(sys.executable).resolve().parent
    else:
        here = Path(__file__).resolve().parent

    pythonw = here / "venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        pythonw = here / "venv" / "Scripts" / "python.exe"

    script = here / "meeting_app.py"

    if not pythonw.exists():
        _show_error("NoteNara — launch failed",
                    f"venv missing. Expected at: {here / 'venv'}")
        return 1
    if not script.exists():
        _show_error("NoteNara — launch failed",
                    f"meeting_app.py not found.\nLooked at: {script}")
        return 1

    # CREATE_NEW_PROCESS_GROUP + CREATE_NO_WINDOW: child is independent of the
    # launcher and runs without any console, but it does NOT detach far enough
    # to lose the AppUserModelID we just set — that's the key vs DETACHED_PROCESS.
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW         = 0x08000000
    flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

    try:
        subprocess.Popen(
            [str(pythonw), str(script)],
            cwd=str(here),
            creationflags=flags,
            close_fds=True,
        )
    except OSError as e:
        _show_error("NoteNara — launch failed", f"Could not start Python.\n\n{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
