# Builds the Scrubs desktop app: desktop/dist/Scrubs/Scrubs.exe, then the MSI installer.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File desktop\build.ps1
# Add -Console to get a console window in the app (shows startup errors).
param([switch]$Console, [switch]$SkipMsi)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
Push-Location $root
try {
    Write-Host "1/4 Frontend: static export to .next-export/"
    $env:STATIC_EXPORT = "1"
    $env:NEXT_PUBLIC_API_URL = "/"          # same origin: the app serves the page and the API
    $env:NEXT_PUBLIC_USE_MOCK = "0"
    npx next build
    if ($LASTEXITCODE -ne 0) { throw "next build failed" }
    Remove-Item Env:STATIC_EXPORT, Env:NEXT_PUBLIC_API_URL, Env:NEXT_PUBLIC_USE_MOCK

    Write-Host "2/4 GLiNER: self-contained model folder"
    & $py desktop\prepare_models.py
    if ($LASTEXITCODE -ne 0) { throw "prepare_models failed" }

    Write-Host "3/4 PyInstaller: desktop/dist/Scrubs"
    if ($Console) { $env:SCRUBS_CONSOLE = "1" }
    & $py -m PyInstaller desktop\scrubs.spec --noconfirm --distpath desktop\dist --workpath desktop\build\pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    Remove-Item Env:SCRUBS_CONSOLE -ErrorAction SilentlyContinue

    if (-not $SkipMsi) {
        Write-Host "4/4 MSI"
        & $py desktop\make_msi.py
        if ($LASTEXITCODE -ne 0) { throw "MSI build failed" }
    }
} finally {
    Pop-Location
}
