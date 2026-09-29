# Generate the sample files used by the manual test checklist.
#
# Usage (from the repository root):
#   .\tools\make-test-files.ps1
#   .\tools\make-test-files.ps1 -OutDir testdata -Force
#
# Files created:
#   sample-ok.txt         small .txt, valid upload
#   sample-bad.png        small .png, should be rejected by the server
#   sample-oversize.txt   60 MB .txt, should be rejected (50 MB limit)
#
# The script is ASCII-only on purpose: Windows PowerShell 5.1 mis-parses
# UTF-8 Chinese text in .ps1 files that have no BOM.

param(
    [string]$OutDir = "testdata",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not [System.IO.Path]::IsPathRooted($OutDir)) {
    $OutDir = Join-Path $repoRoot $OutDir
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Write-TextFile {
    param([string]$Path, [string]$Content, [int]$SizeBytes = 0)

    if ((Test-Path -LiteralPath $Path) -and -not $Force) {
        Write-Output ("skip (exists): " + $Path)
        return
    }

    if ($SizeBytes -gt 0) {
        $stream = [System.IO.File]::Create($Path)
        try {
            $stream.SetLength($SizeBytes)
        }
        finally {
            $stream.Dispose()
        }
    }
    else {
        Set-Content -LiteralPath $Path -Value $Content -Encoding UTF8
    }
    Write-Output ("created: " + $Path)
}

function Write-BinaryFile {
    param([string]$Path, [string]$Base64)

    if ((Test-Path -LiteralPath $Path) -and -not $Force) {
        Write-Output ("skip (exists): " + $Path)
        return
    }

    [System.IO.File]::WriteAllBytes($Path, [System.Convert]::FromBase64String($Base64))
    Write-Output ("created: " + $Path)
}

$tinyPngBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

$okText = "Teaching document sample for manual testing."
$okText = $okText + [Environment]::NewLine + "This .txt file should upload successfully."

Write-TextFile -Path (Join-Path $OutDir "sample-ok.txt") -Content $okText
Write-BinaryFile -Path (Join-Path $OutDir "sample-bad.png") -Base64 $tinyPngBase64
Write-TextFile -Path (Join-Path $OutDir "sample-oversize.txt") -Content "" -SizeBytes (60 * 1024 * 1024)

Write-Output ""
Write-Output ("output folder: " + $OutDir)
Get-ChildItem -LiteralPath $OutDir -File | ForEach-Object {
    Write-Output ("  {0,-22} {1,10:N0} bytes" -f $_.Name, $_.Length)
}
