# Build a standalone Windows bundle: dist\mgridPlayer\mgridPlayer.exe (+ zip).
# Requires 64-bit Python 3.9+ and 64-bit VLC (installer or the official .zip).
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 [-VlcDir "C:\Program Files\VideoLAN\VLC"]
param([string]$VlcDir = $(if ($env:VLC_DIR) { $env:VLC_DIR } else { "C:\Program Files\VideoLAN\VLC" }))
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path (Join-Path $VlcDir "libvlc.dll"))) {
    throw "libvlc.dll not found in '$VlcDir'. Install 64-bit VLC or pass -VlcDir."
}
if (-not (Test-Path ".venv\Scripts\python.exe")) { py -3 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -q --upgrade pip
.\.venv\Scripts\python.exe -m pip install -q -r requirements-dev.txt
.\.venv\Scripts\python.exe packaging\make_icons.py

$env:VLC_DIR = $VlcDir
if (Test-Path dist\mgridPlayer) { Remove-Item -Recurse -Force dist\mgridPlayer }
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\mgridplayer.spec

$version = .\.venv\Scripts\python.exe -c "import mgridplayer; print(mgridplayer.__version__)"
$zip = "dist\mgridPlayer-$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\mgridPlayer -DestinationPath $zip
Write-Host "Bundle: dist\mgridPlayer\mgridPlayer.exe"
Write-Host "Zip:    $zip"
