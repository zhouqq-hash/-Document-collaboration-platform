<#
Start a Cloudflare quick tunnel and print everything needed for WeChat OAuth testing.

Usage (run in the repository root):
  .\tools\wechat-tunnel.ps1              # forwards http://localhost:5000
  .\tools\wechat-tunnel.ps1 -Port 5001   # when the backend uses another port

What it does:
  1. starts a free https tunnel with cloudflared (no account needed);
  2. runs "flask wechat-tunnel --url <tunnel>" and prints the three things to fill in:
     WECHAT_REDIRECT_URI, the domain for the WeChat whitelist, the page URL to open in WeChat;
  3. keeps the tunnel alive until you press Ctrl+C or close the window.

Prerequisite: the backend is running, with WECHAT_* env vars set.

IMPORTANT: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less UTF-8
files as ANSI (GBK on zh-CN systems), and non-ASCII text breaks string parsing,
which shows up as "string is missing the terminator".
#>

param(
    [int]$Port = 5000,
    [string]$Cloudflared = "cloudflared"
)

$ErrorActionPreference = "Stop"

$exe = (Get-Command $Cloudflared -ErrorAction SilentlyContinue).Source
if (-not $exe) {
    foreach ($candidate in @(
            "$env:ProgramFiles\cloudflared\cloudflared.exe",
            "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
            "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe"
        )) {
        if (Test-Path -LiteralPath $candidate) { $exe = $candidate; break }
    }
}
if (-not $exe) {
    Write-Host "cloudflared not found. Install it with:"
    Write-Host "  winget install --id Cloudflare.cloudflared -e"
    exit 1
}

$log = Join-Path $env:TEMP "cloudflared-$Port.log"
if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }

Write-Host "Starting tunnel: $exe tunnel --url http://localhost:$Port"
$proc = Start-Process -FilePath $exe `
    -ArgumentList @("tunnel", "--url", "http://localhost:$Port", "--logfile", $log) `
    -PassThru -WindowStyle Hidden

$url = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path -LiteralPath $log) {
        $match = Select-String -LiteralPath $log `
            -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches |
            Select-Object -First 1
        if ($match) { $url = $match.Matches[0].Value; break }
    }
}

if (-not $url) {
    Write-Host "Could not read the tunnel URL. Log file: $log"
    if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 15 }
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    exit 1
}

$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$appPath = Join-Path $PSScriptRoot "..\backend\run.py"

Write-Host ""
Write-Host "Tunnel is up: $url"
Write-Host "(log: $log - closing this window stops the tunnel)"
Write-Host ""

& $python -m flask --app $appPath wechat-tunnel --url $url

Write-Host ""
Write-Host "Next: apply the env var from step 1, restart the backend, then put the domain"
Write-Host "from step 2 into the WeChat callback whitelist, and open the step 3 URL in WeChat."
Write-Host "Press Ctrl+C to stop (this also stops the tunnel)."

try {
    Wait-Process -Id $proc.Id
}
finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    Write-Host "Tunnel stopped."
}
