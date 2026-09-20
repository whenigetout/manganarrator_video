param(
    [switch]$NoBrowser,
    [switch]$AccessLog,
    [string]$Title = 'MangaNarrator Studio - backend + frontend (one server)'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
. (Join-Path $PSScriptRoot 'studio_env.ps1')

$logFile = Get-StudioLogFile -Root $root -Prefix 'studio'

function Write-StudioLog {
    param(
        [string]$Message,
        [string]$Color = 'Gray'
    )
    $line = (Get-Date -Format 'HH:mm:ss') + ' ' + $Message
    Write-Host $line -ForegroundColor $Color
    try { Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8 } catch { }
}

function Invoke-StudioCommand {
    # Run a tool and mirror its output to the console and the studio log file.
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $ErrorActionPreference = 'Continue'
    & $FilePath @Arguments 2>&1 | ForEach-Object {
        $text = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { $_.ToString() }
        Write-Host $text
        try { Add-Content -LiteralPath $logFile -Value $text -Encoding UTF8 } catch { }
    }
}

try {
    try { $Host.UI.RawUI.WindowTitle = $Title } catch { }
    Write-StudioLog 'MangaNarrator Audio Studio launcher' 'Cyan'
    Write-StudioLog ('Started:    ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    Write-StudioLog ('Repository: ' + $root)
    Write-StudioLog ('Log file:   ' + $logFile)

    $python = Get-StudioPython
    if (-not $python) { throw 'Conda environment not found. Activate manganarrator-video first, or set STUDIO_PYTHON to its python.exe.' }
    Write-StudioLog ('Python:     ' + $python)
    $prefix = Split-Path -Parent $python
    $env:PATH = "$prefix;$prefix\Scripts;$prefix\Library\bin;$env:PATH"

    & $python -c 'import fastapi, uvicorn, mn_contracts, numpy; from app.config import VideoConfig; VideoConfig()'
    if ($LASTEXITCODE -ne 0) {
        throw ('The backend environment is incomplete (see the traceback above). Install the base requirements with: "' + $python + '" -m pip install -r requirements.txt')
    }
    foreach ($tool in @('ffmpeg','ffprobe','node','npm.cmd')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool not found. Install FFmpeg and Node.js (20.19+ or 22.12+) and reopen the launcher." }
    }
    $publishingModules = @('google_auth_oauthlib','httpx','keyring','filelock','importlib_metadata')
    $missing = @(& $python -c 'import importlib.util as u, sys; print(*[n for n in sys.argv[1:] if u.find_spec(n) is None])' @publishingModules) -split '\s+' | Where-Object { $_ }
    if ($missing.Count) {
        Write-StudioLog ('Installing missing publishing dependencies (' + ($missing -join ', ') + ')...') 'Yellow'
        Invoke-StudioCommand -FilePath $python -Arguments @('-m','pip','install','-r','requirements-publishing.txt')
        if ($LASTEXITCODE -ne 0) {
            throw ('Publishing dependencies are missing (' + ($missing -join ', ') + ') and the install failed. Check the network and run: "' + $python + '" -m pip install -r requirements-publishing.txt')
        }
    }
    Push-Location -LiteralPath (Join-Path $root 'frontend')
    try {
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        try { $lockHash = [BitConverter]::ToString($hasher.ComputeHash([System.IO.File]::ReadAllBytes((Join-Path $root 'frontend/package-lock.json')))) }
        finally { $hasher.Dispose() }
        $stamp = 'node_modules/.studio-lock-hash'
        if (-not (Test-Path -LiteralPath $stamp) -or (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $lockHash) {
            Write-StudioLog 'Installing frontend dependencies (npm ci)...' 'Yellow'
            Invoke-StudioCommand -FilePath 'npm.cmd' -Arguments @('ci','--no-audit','--no-fund')
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
            Set-Content -LiteralPath $stamp -Value $lockHash
        }
        $dist = 'dist/index.html'
        $latest = Get-ChildItem -LiteralPath 'src' -File -Recurse | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        $needsBuild = -not (Test-Path -LiteralPath $dist)
        if (-not $needsBuild) {
            $built = (Get-Item -LiteralPath $dist).LastWriteTimeUtc
            $needsBuild = $latest.LastWriteTimeUtc -gt $built -or (Get-Item -LiteralPath 'package-lock.json').LastWriteTimeUtc -gt $built -or (Get-Item -LiteralPath 'vite.config.js').LastWriteTimeUtc -gt $built -or (Get-Item -LiteralPath 'index.html').LastWriteTimeUtc -gt $built
        }
        if ($needsBuild) {
            Write-StudioLog 'Building the React studio (npm run build)...' 'Yellow'
            Invoke-StudioCommand -FilePath 'npm.cmd' -Arguments @('run','build')
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        } else {
            Write-StudioLog 'Frontend build is up to date.'
        }
    } finally { Pop-Location }
    $arguments = @('scripts/launch_studio.py')
    if ($NoBrowser) { $arguments += '--no-browser' }
    if ($AccessLog) { $arguments += '--access-log' }
    Write-StudioLog 'Starting the studio server. Keep this window open; Ctrl+C stops it.' 'Cyan'
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw ('Studio stopped with an error (exit code ' + $LASTEXITCODE + ').') }
    Write-StudioLog ('Studio stopped. Full log: ' + $logFile) 'Yellow'
} catch {
    Write-StudioLog $_.Exception.Message 'Red'
    Write-StudioLog ('Full log: ' + $logFile) 'Red'
    exit 1
}
