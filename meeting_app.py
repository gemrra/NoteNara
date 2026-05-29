#!/usr/bin/env python3
"""NoteNara — thin entrypoint.

All implementation lives under app/. Run this file (or use NoteNara.bat)
to launch the GUI.
"""

import sys

from app.ui.app import App


def _set_windows_app_id() -> None:
    """Tell Windows we're our own app, not a Python child.

    Without this, Windows groups our window under python.exe in the taskbar
    and uses the python feather icon — even after iconbitmap. Setting the
    AppUserModelID before any window is created makes the taskbar treat
    NoteNara as its own app and pick up the .ico we registered.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "com.notenara.app.v2")
    except (AttributeError, OSError):
        pass


def main() -> None:
    _set_windows_app_id()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
