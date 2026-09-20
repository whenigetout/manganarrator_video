param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
try {
    $candidates = @($env:STUDIO_PYTHON)
    $candidates += @(
        (Join-Path $env:USERPROFILE 'miniconda3\envs\manganarrator-video\python.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3\envs\manganarrator-video\python.exe')
    )
    if ($env:CONDA_PREFIX) { $candidates += Join-Path $env:CONDA_PREFIX 'python.exe' }
    $python = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $python) { throw 'Conda environment not found. Activate manganarrator-video first, or set STUDIO_PYTHON to its python.exe.' }
    $prefix = Split-Path -Parent $python
    $env:PATH = "$prefix;$prefix\Scripts;$prefix\Library\bin;$env:PATH"
    & $python -c 'import fastapi, uvicorn, mn_contracts, cv2, numpy; from app.config import VideoConfig; VideoConfig()'
    if ($LASTEXITCODE -ne 0) { throw 'The existing backend environment/config is incomplete. See README.md for the base project setup.' }
    foreach ($tool in @('ffmpeg','ffprobe','node','npm.cmd')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool not found. Install FFmpeg and Node.js (20.19+ or 22.12+) and reopen the launcher." }
    }
    & $python -c 'import google_auth_oauthlib, httpx, keyring, filelock'
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing optional publishing dependencies...'
        & $python -m pip install -r requirements-publishing.txt
        if ($LASTEXITCODE -ne 0) { throw 'Publishing dependency installation failed. Check the network and try again.' }
    }
    Push-Location -LiteralPath (Join-Path $root 'frontend')
    try {
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        try { $lockHash = [BitConverter]::ToString($hasher.ComputeHash([System.IO.File]::ReadAllBytes((Join-Path $root 'frontend/package-lock.json')))) }
        finally { $hasher.Dispose() }
        $stamp = 'node_modules/.studio-lock-hash'
        if (-not (Test-Path -LiteralPath $stamp) -or (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $lockHash) {
            Write-Host 'Installing frontend dependencies...'
            & npm.cmd ci --no-audit --no-fund
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
            Write-Host 'Building the React studio...'
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        }
    } finally { Pop-Location }
    $arguments = @('scripts/launch_studio.py')
    if ($NoBrowser) { $arguments += '--no-browser' }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Studio stopped with an error. See the message above.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
