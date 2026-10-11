<#
One-command WeChat live-login launcher.

What it does, in order:
  1. starts a free Cloudflare quick tunnel to http://127.0.0.1:<Port>;
  2. reads WeChat credentials from tools\wechat-live.local.env (or prompts);
  3. exports WECHAT_* env vars for this run (backend inherits them);
  4. prints the redirect URI / whitelist domain / page URL to fill in;
  5. runs the Flask backend in the foreground.

Press Ctrl+C to stop: it also stops the tunnel.

Usage (run in the repository root):
  .\tools\wechat-live.ps1
  .\tools\wechat-live.ps1 -Port 5001

Credentials live in tools\wechat-live.local.env (git-ignored), one per line:
  WECHAT_APP_ID=wx....
  WECHAT_APP_SECRET=....
  WECHAT_AUTHORIZE_MODE=mp
If the file is missing, the script prompts and offers to save it.

The Chinese "what to fill in" output is printed by the Flask CLI
(flask wechat-tunnel), not by this file.

IMPORTANT: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less
UTF-8 files as ANSI (GBK on zh-CN systems); non-ASCII text breaks string
parsing and shows up as "string is missing the terminator".
#>

param(
    [int]$Port = 5000,
    [string]$Cloudflared = "cloudflared"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$appPath = Join-Path $root "backend\run.py"
$envFile = Join-Path $PSScriptRoot "wechat-live.local.env"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Python venv not found: $python"
    Write-Host "Create it once with:"
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt"
    exit 1
}

function Read-EnvFile([string]$path) {
    $values = @{}
    if (-not (Test-Path -LiteralPath $path)) { return $values }
    foreach ($line in Get-Content -LiteralPath $path) {
        $text = $line.Trim()
        if (-not $text -or $text.StartsWith("#")) { continue }
        $idx = $text.IndexOf("=")
        if ($idx -lt 1) { continue }
        $values[$text.Substring(0, $idx).Trim()] = $text.Substring($idx + 1).Trim()
    }
    return $values
}

function Save-EnvFile([string]$path, [string]$appId, [string]$secret, [string]$mode) {
    $lines = @(
        "# Local WeChat live-test credentials. Git-ignored; never commit.",
        "WECHAT_APP_ID=$appId",
        "WECHAT_APP_SECRET=$secret",
        "WECHAT_AUTHORIZE_MODE=$mode"
    )
    Set-Content -LiteralPath $path -Value $lines -Encoding ASCII
}

$creds = Read-EnvFile $envFile
$appId = $creds["WECHAT_APP_ID"]
$appSecret = $creds["WECHAT_APP_SECRET"]
$mode = $creds["WECHAT_AUTHORIZE_MODE"]
if (-not $mode) { $mode = "mp" }

$saveAfterPrompt = $false
if (-not $appId) {
    $appId = (Read-Host "WECHAT_APP_ID (WeChat test account appID)").Trim()
    $saveAfterPrompt = $true
}
if (-not $appSecret) {
    $appSecret = (Read-Host "WECHAT_APP_SECRET").Trim()
    $saveAfterPrompt = $true
}
if (-not $appId -or -not $appSecret) {
    Write-Host "Missing WECHAT_APP_ID / WECHAT_APP_SECRET. Put them in $envFile or type them above."
    exit 1
}
if ($saveAfterPrompt) {
    Save-EnvFile $envFile $appId $appSecret $mode
    Write-Host "Saved credentials to $envFile (git-ignored)."
}

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

$log = Join-Path $env:TEMP "cloudflared-live-$Port.log"
if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }

Write-Host "Starting tunnel: $exe tunnel --url http://127.0.0.1:$Port"
$tunnel = Start-Process -FilePath $exe `
    -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$Port", "--logfile", $log, "--no-autoupdate") `
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
    Write-Host "Could not read the tunnel URL. Log: $log"
    if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 15 }
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force }
    exit 1
}

$redirectUri = "$url/api/auth/wechat/callback"

$env:WECHAT_APP_ID = $appId
$env:WECHAT_APP_SECRET = $appSecret
$env:WECHAT_AUTHORIZE_MODE = $mode
$env:WECHAT_REDIRECT_URI = $redirectUri

Write-Host ""
Write-Host "Tunnel is up: $url"
Write-Host ""

& $python -m flask --app $appPath wechat-tunnel --url $url

Write-Host ""
Write-Host "Starting backend on http://127.0.0.1:$Port ... (Ctrl+C stops backend + tunnel)"
Write-Host ""

try {
    & $python -m flask --app $appPath run --host 127.0.0.1 --port $Port --no-reload --no-debugger
}
finally {
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force }
    Write-Host "Backend and tunnel stopped."
}
