# Generate src\pysidedeploy.ci.spec from src\pysidedeploy.spec for a build on another
# machine (GitHub Actions runner). The checked-in spec carries absolute paths of the
# developer machine -- exec_directory, icon, python_path and --include-data-dir inside
# extra_args -- so everything under the old repository root is rebased onto the new one
# and python_path is pointed at the interpreter that runs the build.
#
# Usage:  pwsh tools\make_ci_spec.ps1 -RepositoryRoot . -PythonPath (Get-Command python).Source
#
# NOTE: keep this script ASCII-only -- Windows PowerShell 5.1 reads .ps1 in the system
# codepage, and non-ASCII (Cyrillic) breaks the parser.
[CmdletBinding()]
param(
    [string] $RepositoryRoot = $PSScriptRoot + "\..",
    [string] $PythonPath
)
$ErrorActionPreference = "Stop"

$root = (Resolve-Path $RepositoryRoot).Path.TrimEnd("\")
$source = Join-Path $root "src\pysidedeploy.spec"
$target = Join-Path $root "src\pysidedeploy.ci.spec"
if (-not $PythonPath) { $PythonPath = (Get-Command python).Source }

if (-not (Test-Path $source)) { throw "spec not found: $source" }

$text = Get-Content -Path $source -Raw -Encoding Ascii

# Old repository root, in both slash flavours the spec mixes (icon uses "\", the
# --include-data-dir argument uses "/"). Any absolute path pointing into the old
# checkout is rewritten to the same relative place under the new root.
$oldRootPattern = '[A-Za-z]:[\\/](?:[^\\/\r\n=]+[\\/])*M4\.DayZ\.CE\.Map\.Editor'
$text = [System.Text.RegularExpressions.Regex]::Replace(
    $text, $oldRootPattern, { param($match) $root }, "IgnoreCase")

# python_path pointed at the developer .venv, which does not exist on the runner.
$text = [System.Text.RegularExpressions.Regex]::Replace(
    $text, '(?m)^python_path\s*=.*$', "python_path = $PythonPath")

# pyside6-deploy reads the spec as cp1252, so keep the generated file ASCII too.
[System.IO.File]::WriteAllText($target, $text, [System.Text.Encoding]::ASCII)

Write-Host "spec written: $target"
Write-Host "  root        -> $root"
Write-Host "  python_path -> $PythonPath"
