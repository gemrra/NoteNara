# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a self-contained NoteNara --onedir bundle.

Build:
    venv\\Scripts\\python.exe -m PyInstaller NoteNara.spec --noconfirm --clean

Output:
    dist/NoteNara/NoteNara.exe   (+ _internal/ with all deps)

The bundle includes the Python runtime, all dependencies, the CUDA runtime
DLLs (cublas / cudnn / nvrtc) so GPU transcription works without the user
installing CUDA, the app assets (logo / icon), and the tkdnd drag-and-drop
binaries. The Whisper model itself is NOT bundled — it downloads on first
transcription into <exe-dir>/models (keeps the bundle ~2 GB instead of 3 GB).
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)
SITE = ROOT / "venv" / "Lib" / "site-packages"

# ---------------------------------------------------------------------------
# Collect heavyweight packages (data + binaries + hidden imports) the robust
# way — let PyInstaller's hooks gather everything each package needs.
# ---------------------------------------------------------------------------
datas = []
binaries = []
hiddenimports = []

for pkg in ("faster_whisper", "ctranslate2", "av", "onnxruntime",
            "tkinterdnd2"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# PIL submodules occasionally missed by static analysis.
hiddenimports += collect_submodules("PIL")

# ---------------------------------------------------------------------------
# App assets — keep the app/assets/ layout so constants.ASSETS_DIR resolves.
# ---------------------------------------------------------------------------
assets_dir = ROOT / "app" / "assets"
for f in assets_dir.iterdir():
    if f.is_file():
        datas.append((str(f), "app/assets"))

# Ship the example config so first-run users have a reference.
example_cfg = ROOT / "meeting_app_config.example.json"
if example_cfg.exists():
    datas.append((str(example_cfg), "."))

# ---------------------------------------------------------------------------
# CUDA runtime DLLs — bundle under nvidia/<pkg>/bin to mirror the venv layout
# that services/whisper.py setup_cuda_dlls() walks. ~1.9 GB; this is what
# lets GPU transcription run on a machine with no CUDA toolkit installed.
# ---------------------------------------------------------------------------
nvidia_root = SITE / "nvidia"
if nvidia_root.exists():
    for pkg_dir in nvidia_root.iterdir():
        bin_dir = pkg_dir / "bin"
        if not bin_dir.is_dir():
            continue
        for dll in bin_dir.glob("*.dll"):
            # dest preserves nvidia/<pkg>/bin/<dll>
            dest = f"nvidia/{pkg_dir.name}/bin"
            binaries.append((str(dll), dest))


a = Analysis(
    ["meeting_app.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim obvious dead weight that sometimes gets pulled in.
        "matplotlib", "pytest", "IPython", "notebook", "pandas",
        "scipy", "sympy",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NoteNara",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # UPX can trip antivirus — leave off
    console=False,                   # GUI app, no console window
    icon=str(ROOT / "app" / "assets" / "NoteNara.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NoteNara",
)
