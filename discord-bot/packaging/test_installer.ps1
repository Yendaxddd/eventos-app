# Installs the freshly built installer into a temp folder and checks what a user would rely on:
# shortcuts, the installed app starts, an update keeps user data, uninstalling keeps user data.
# Meant for CI. Locally it needs -Force, because it installs and uninstalls under the app's real AppId.
param([switch]$Force)
$ErrorActionPreference = "Stop"

if (-not $env:CI -and -not $Force) { throw "This test installs and uninstalls the app; run it with -Force to confirm." }

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$setup = Get-ChildItem (Join-Path $root "dist") -Filter "EventosApp-Setup-*.exe" | Select-Object -First 1
if (-not $setup) { throw "No EventosApp-Setup-*.exe found in dist" }

$base = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$dir = Join-Path $base "EventosAppInstallTest"
$log = Join-Path $base "installer-test.log"
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Eventos App.lnk"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Eventos App.lnk"

function Check($condition, $what) {
    if (-not $condition) { throw "FAILED: $what" }
    Write-Host "ok: $what"
}

function Install-App {
    $p = Start-Process -FilePath $setup.FullName -Wait -PassThru -ArgumentList `
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=`"$dir`"", "/LOG=`"$log`""
    Check ($p.ExitCode -eq 0) "installer exits with code 0 (got $($p.ExitCode))"
}

try {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }

    Write-Host "== 1. Fresh install"
    Install-App
    Check (Test-Path (Join-Path $dir "EventosApp.exe")) "EventosApp.exe installed"
    Check (Test-Path (Join-Path $dir "_internal")) "runtime folder installed"
    Check (Test-Path (Join-Path $dir "data\player_stats.json")) "default data installed"
    Check (Test-Path (Join-Path $dir "assets\Domain clash.gif")) "default assets installed"
    Check (Test-Path (Join-Path $dir "unins000.exe")) "uninstaller installed"
    Check (Test-Path $startMenu) "Start menu shortcut exists"
    Check (Test-Path $desktop) "desktop shortcut exists"

    Write-Host "== 2. The installed app starts"
    $smoke = Join-Path $base "smoke_installed.json"
    $p = Start-Process -FilePath (Join-Path $dir "EventosApp.exe") -Wait -PassThru -ArgumentList "--smoke-test", "--smoke-out", $smoke
    if (Test-Path $smoke) { Get-Content $smoke }
    Check ($p.ExitCode -eq 0) "installed app passes its smoke test"

    Write-Host "== 3. Simulate a user's data and an old runtime"
    Set-Content (Join-Path $dir "data\player_stats.json") '{"123": {"marker": "keep-me"}}' -Encoding UTF8
    Set-Content (Join-Path $dir "settings.json") '{"discord_token": "keep-me"}' -Encoding UTF8
    New-Item -ItemType Directory -Force (Join-Path $dir "assets\counter_gifs") | Out-Null
    Set-Content (Join-Path $dir "assets\counter_gifs\added_by_gm.txt") "keep-me" -Encoding UTF8
    Set-Content (Join-Path $dir "_internal\stale_old_file.dll") "old" -Encoding UTF8

    Write-Host "== 4. Update over the existing install"
    Install-App
    Check ((Get-Content (Join-Path $dir "data\player_stats.json") -Raw) -match "keep-me") "update keeps edited player data"
    Check ((Get-Content (Join-Path $dir "settings.json") -Raw) -match "keep-me") "update keeps settings.json"
    Check (Test-Path (Join-Path $dir "assets\counter_gifs\added_by_gm.txt")) "update keeps GIFs added by users"
    Check (-not (Test-Path (Join-Path $dir "_internal\stale_old_file.dll"))) "update clears the old runtime"
    Check (Test-Path (Join-Path $dir "EventosApp.exe")) "app still installed after update"

    Write-Host "== 5. Uninstall (silent: keeps user data)"
    # The uninstaller relaunches itself from a temp copy, so Start-Process -Wait returns early: poll instead.
    Start-Process -FilePath (Join-Path $dir "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
    $deadline = (Get-Date).AddSeconds(120)
    while ((Test-Path (Join-Path $dir "EventosApp.exe")) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 3
    Check (-not (Test-Path (Join-Path $dir "EventosApp.exe"))) "EventosApp.exe removed"
    Check (-not (Test-Path (Join-Path $dir "_internal"))) "runtime folder removed"
    Check (-not (Test-Path $startMenu)) "Start menu shortcut removed"
    Check (-not (Test-Path $desktop)) "desktop shortcut removed"
    Check ((Get-Content (Join-Path $dir "data\player_stats.json") -Raw) -match "keep-me") "uninstall keeps player data"
    Check (Test-Path (Join-Path $dir "settings.json")) "uninstall keeps settings.json"
    Write-Host "Installer test passed."
}
catch {
    Write-Host "Installer test failed: $_"
    if (Test-Path $log) { Write-Host "---- last lines of the installer log"; Get-Content $log -Tail 40 }
    throw
}
finally {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue }
}
