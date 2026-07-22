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
# checkout is rewritten to the same relative place under the new root -- keeping the
# slash flavour of the path it replaces. That is not cosmetic: pyside6-deploy splits
# extra_args with shlex in posix mode, where "\" escapes the next character, so a
# backslash path there arrives at Nuitka with its separators eaten
# ("D:\a\repo\assets" -> "D:arepoassets") and the build dies on --include-data-dir.
$rootForwardSlash = $root -replace '\\', '/'
$oldRootPattern = '[A-Za-z]:[\\/](?:[^\\/\r\n=]+[\\/])*M4\.DayZ\.CE\.Map\.Editor'
$text = [System.Text.RegularExpressions.Regex]::Replace(
    $text, $oldRootPattern,
    { param($match) if ($match.Value.Contains("/")) { $rootForwardSlash } else { $root } },
    "IgnoreCase")

# python_path pointed at the developer .venv, which does not exist on the runner.
$text = [System.Text.RegularExpressions.Regex]::Replace(
    $text, '(?m)^python_path\s*=.*$', "python_path = $PythonPath")

# --quiet keeps the local build readable, but on a runner the Nuitka log is the only way
# to see why a build produced nothing, so drop it.
$text = [System.Text.RegularExpressions.Regex]::Replace(
    $text, '(?m)^(extra_args\s*=.*?)\s--quiet\b', '$1')

# Fail here, not inside Nuitka a minute later: every --include-data-dir source must exist
# after the rebase. This is what catches a path mangled by the rewrite.
foreach ($match in [regex]::Matches($text, '--include-data-dir=([^=\s]+)=')) {
    $dataDir = $match.Groups[1].Value
    if (-not (Test-Path $dataDir)) { throw "--include-data-dir points at a missing directory: $dataDir" }
}

# pyside6-deploy reads the spec as cp1252, so keep the generated file ASCII too.
[System.IO.File]::WriteAllText($target, $text, [System.Text.Encoding]::ASCII)

Write-Host "spec written: $target"
Write-Host "  root        -> $root"
Write-Host "  python_path -> $PythonPath"
