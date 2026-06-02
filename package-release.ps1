# package-release.ps1
# ---------------------------------------------------------------------------
# Zips the PyInstaller bundle in dist/NoteNara into a release archive ready to
# attach to a GitHub Release. Run AFTER:
#     venv\Scripts\python.exe -m PyInstaller NoteNara.spec --noconfirm --clean
#
# Output: NoteNara-vX.Y.Z-win64.zip in the repo root.
# ---------------------------------------------------------------------------
param(
    [string]$Version = "2.1.0"
)

$ErrorActionPreference = "Stop"
$root  = $PSScriptRoot
$dist  = Join-Path $root "dist\NoteNara"
$zip   = Join-Path $root "NoteNara-v$Version-win64.zip"

if (-not (Test-Path $dist)) {
    Write-Error "dist\NoteNara not found. Build first: python -m PyInstaller NoteNara.spec --noconfirm --clean"
    exit 1
}

Write-Host "Bundle size:" -ForegroundColor Yellow
"  {0:N1} GB" -f ((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum / 1GB)

if (Test-Path $zip) { Remove-Item $zip -Force }

Write-Host ""
Write-Host "Compressing to $zip (this takes a few minutes)..." -ForegroundColor Yellow
Compress-Archive -Path $dist -DestinationPath $zip -CompressionLevel Optimal

$zipSize = (Get-Item $zip).Length / 1GB
Write-Host ""
Write-Host "Done." -ForegroundColor Green
"  archive: $zip"
"  size:    {0:N1} GB" -f $zipSize

if ($zipSize -gt 2.0) {
    Write-Host ""
    Write-Host "[WARN] Archive over 2 GB - GitHub per-file release limit is 2 GB." -ForegroundColor Red
    Write-Host "       Consider a CPU-only build, or split with 7-Zip volumes." -ForegroundColor Red
}

Write-Host ""
Write-Host "Next: create a GitHub Release and attach the .zip:" -ForegroundColor Cyan
Write-Host "  1. https://github.com/gemrra/NoteNara/releases/new"
Write-Host "  2. Tag: v$Version   Title: NoteNara v$Version"
Write-Host "  3. Drag the .zip into the assets box"
Write-Host "  4. Paste RELEASE_NOTES.md as the description"
Write-Host "  5. Publish"
