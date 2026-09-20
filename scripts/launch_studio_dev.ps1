param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
. (Join-Path $PSScriptRoot 'studio_env.ps1')

$logFile = Get-StudioLogFile -Root $root -Prefix 'studio'
$stateFile = Join-Path $env:LOCALAPPDATA 'MangaNarrator\publishing\launcher.json'

function Test-StudioUrl {
    param([string]$Url)
    try {
        Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-StudioStatePort {
    param([string]$StateFile)
    if (-not (Test-Path -LiteralPath $StateFile)) { return $null }
    try {
        $state = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        if ($state.port) { return [int]$state.port }
    } catch { }
    return $null
}

try {
    try { $Host.UI.RawUI.WindowTitle = 'MangaNarrator Studio - dev launcher' } catch { }
    Write-Host 'MangaNarrator Audio Studio - dev mode' -ForegroundColor Cyan
    Write-Host 'Backend and frontend each get their own console window.'
    Write-Host ('Backend log file: ' + $logFile)
    Write-Host ''

    Start-Process -FilePath (Join-Path $PSScriptRoot 'studio_backend.cmd') -WorkingDirectory $root
    Write-Host 'Backend console opened. Waiting for the API to answer...'
    $backendUrl = $null
    $started = Get-Date
    $lastNotice = Get-Date
    $deadline = (Get-Date).AddSeconds(300)
    while (-not $backendUrl -and (Get-Date) -lt $deadline) {
        $ports = @((Get-StudioStatePort -StateFile $stateFile), $env:STUDIO_PORT, 8084) | Where-Object { $_ } | Select-Object -Unique
        foreach ($candidate in $ports) {
            $url = "http://127.0.0.1:$candidate/studio/"
            if (Test-StudioUrl -Url $url) { $backendUrl = $url; break }
        }
        if (-not $backendUrl) {
            if (((Get-Date) - $lastNotice).TotalSeconds -ge 15) {
                Write-Host ('  still starting (' + [int]((Get-Date) - $started).TotalSeconds + 's) - the backend window shows what it is doing.')
                $lastNotice = Get-Date
            }
            Start-Sleep -Milliseconds 750
        }
    }
    if (-not $backendUrl) { throw 'The backend did not answer within five minutes. Check the backend console window and the log file above.' }
    Write-Host ('Backend is up: ' + $backendUrl) -ForegroundColor Green

    Start-Process -FilePath (Join-Path $PSScriptRoot 'studio_frontend.cmd') -WorkingDirectory (Join-Path $root 'frontend')
    Write-Host 'Frontend console opened. Waiting for the Vite dev server on http://127.0.0.1:5173/ ...'
    $devUrl = 'http://127.0.0.1:5173/'
    $started = Get-Date
    $lastNotice = Get-Date
    $deadline = (Get-Date).AddSeconds(180)
    while (-not (Test-StudioUrl -Url $devUrl) -and (Get-Date) -lt $deadline) {
        if (((Get-Date) - $lastNotice).TotalSeconds -ge 15) {
            Write-Host ('  still starting (' + [int]((Get-Date) - $started).TotalSeconds + 's) - the frontend window shows what it is doing.')
            $lastNotice = Get-Date
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-StudioUrl -Url $devUrl)) { throw 'Vite did not answer on http://127.0.0.1:5173/. Check the frontend console window; the port may be in use.' }

    $openUrl = $devUrl
    if (-not $NoBrowser) {
        $token = ''
        $python = Get-StudioPython
        if ($python) {
            try {
                $token = & $python -c "import sys; sys.path.insert(0, r'$root'); from app.publishing.settings import Settings; print(Settings().owner_key())"
            } catch {
                $token = ''
            }
        }
        if ("$token".Trim()) {
            $openUrl = $devUrl + '#publishingToken=' + "$token".Trim()
        } else {
            Write-Host 'Publishing will stay locked here. Run Launch Studio.cmd once to unlock it, then reload this page.' -ForegroundColor Yellow
        }
        Start-Process $openUrl
    }

    Write-Host ''
    Write-Host ('Dev UI (Vite, hot reload): ' + $devUrl) -ForegroundColor Green
    Write-Host ('Backend/API console:       ' + $backendUrl) -ForegroundColor Green
    Write-Host ('Backend log file:          ' + $logFile)
    Write-Host 'Close both console windows to stop the studio.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
