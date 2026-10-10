# Builds dist\EventosApp\EventosApp.exe (a windowed app, no terminal) and zips it.
# Run from anywhere:   powershell -ExecutionPolicy Bypass -File discord-bot\packaging\build_windows.ps1
# Needs Python 3.11+ on PATH. CI runs this same script.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

Write-Host "==> Installing build dependencies"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-desktop.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "==> Building EventosApp.exe"
python -m PyInstaller packaging\EventosApp.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# assets/ (GIFs) and data/ (game config) stay as plain folders next to the exe, so they can be
# edited and backed up, instead of being buried inside the bundle.
$out = Join-Path $root "dist\EventosApp"
foreach ($name in "assets", "data") {
    Write-Host "==> Copying $name"
    Copy-Item -Recurse -Force (Join-Path $root $name) (Join-Path $out $name)
}
Copy-Item -Force (Join-Path $root "packaging\LEEME.txt") (Join-Path $out "LEEME.txt")

Write-Host "==> Zipping"
$zip = Join-Path $root "dist\EventosApp-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $out -DestinationPath $zip
Write-Host "Done: $zip"
