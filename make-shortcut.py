"""Create NoteNara.lnk with AppUserModelID property set.

Windows uses the shortcut's AppID (System.AppUserModel.ID property) to decide
which taskbar slot a launched app belongs to. If the .lnk has the same AppID
that meeting_app.py sets via SetCurrentProcessExplicitAppUserModelID, the
pinned shortcut and the running app share one slot with the correct icon.

Without this, pinning the bare NoteNara.exe creates a shortcut with no AppID
property — Windows falls back to icon-by-target-path, which gets confused
when the launcher spawns pythonw (different exe → different default icon).
"""
from pathlib import Path
from win32com.shell import shell, shellcon
import pythoncom
from win32com.propsys import propsys, pscon

APP_ID = "com.notenara.app.v2"
here = Path(r"E:\AILocal\NoteNara")

target  = here / "NoteNara.exe"
lnkpath = here / "NoteNara.lnk"
icon    = here / "app" / "assets" / "NoteNara.ico"

# 1. Build IShellLink + IPersistFile to point at NoteNara.exe.
link = pythoncom.CoCreateInstance(
    shell.CLSID_ShellLink, None,
    pythoncom.CLSCTX_INPROC_SERVER,
    shell.IID_IShellLink)
link.SetPath(str(target))
link.SetWorkingDirectory(str(here))
link.SetIconLocation(str(icon), 0)
link.SetDescription("NoteNara — Meeting transcriber")

# 2. Cast to IPropertyStore and set the AppUserModel.ID property.
ps = link.QueryInterface(propsys.IID_IPropertyStore)
# PKEY_AppUserModel_ID = {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, pid 5
PKEY_AppUserModel_ID = pscon.PKEY_AppUserModel_ID
ps.SetValue(PKEY_AppUserModel_ID,
            propsys.PROPVARIANTType(APP_ID, pythoncom.VT_BSTR))
ps.Commit()

# 3. Persist to disk.
persist = link.QueryInterface(pythoncom.IID_IPersistFile)
persist.Save(str(lnkpath), 0)

print(f"Wrote {lnkpath} (target: {target.name}, AppID: {APP_ID})")
