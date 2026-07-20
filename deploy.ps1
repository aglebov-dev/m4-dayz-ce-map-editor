# Build the editor .exe via pyside6-deploy (Nuitka backend).
# Run from the repo root:  ./deploy.ps1
# Build config lives in src\pysidedeploy.spec. The exe is written to .\dist\.
# NOTE: keep this script ASCII-only -- Windows PowerShell 5.1 reads .ps1 in the system
# codepage, and non-ASCII (Cyrillic) breaks the parser.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$deploy = Join-Path $root ".venv\Scripts\pyside6-deploy.exe"
if (-not (Test-Path $deploy)) {
    Write-Error "pyside6-deploy not found at $deploy. Create the env first: rebuild-env.bat"
    exit 1
}
# pyside6-deploy copies the built exe into exec_directory but does NOT create it.
# Make sure dist\ exists, else finalize() fails with FileNotFoundError on the copy.
$dist = Join-Path $root "dist"
if (-not (Test-Path $dist)) {
    New-Item -ItemType Directory -Path $dist | Out-Null
}
# pyside6-deploy expects input_file (app.py) and the .spec in the current dir -> run from src\
Push-Location (Join-Path $root "src")
try {
    & $deploy -c pysidedeploy.spec --keep-deployment-files
}
finally {
    Pop-Location
}
Write-Host ""
Write-Host "Done. exe: $(Join-Path $root 'dist')" -ForegroundColor Green
