# Builds dist\EventosApp\EventosApp.exe (a windowed app, no terminal), a zip, and the installer.
# Run from anywhere:   powershell -ExecutionPolicy Bypass -File discord-bot\packaging\build_windows.ps1
# Needs Python 3.11+ on PATH, and Inno Setup 6 for the installer (https://jrsoftware.org/isdl.php or
# `choco install innosetup`). Without Inno Setup the installer is skipped unless -RequireInstaller is given.
# CI runs this same script.
param([switch]$RequireInstaller)
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
Write-Host "Zip: $zip"

Write-Host "==> Building installer"
$version = (python -c "from eventos_app import __version__; print(__version__)").Trim()
$candidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path $_) }
if (-not $candidates) {
    $msg = "Inno Setup 6 not found: skipping the installer. Install it with 'choco install innosetup'."
    if ($RequireInstaller) { throw $msg }
    Write-Warning $msg
} else {
    & ($candidates | Select-Object -First 1) "/DAppVersion=$version" (Join-Path $root "packaging\EventosApp.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer: $(Join-Path $root "dist\EventosApp-Setup-$version.exe")"
}
Write-Host "Done."
