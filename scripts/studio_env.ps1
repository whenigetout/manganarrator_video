# Shared helpers for the MangaNarrator Studio launchers.

function Get-StudioPython {
    # Explicit override, then the environment the user activated, then defaults.
    $candidates = @($env:STUDIO_PYTHON)
    if ($env:CONDA_PREFIX) { $candidates += Join-Path $env:CONDA_PREFIX 'python.exe' }
    $candidates += @(
        (Join-Path $env:USERPROFILE 'miniconda3\envs\manganarrator-video\python.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3\envs\manganarrator-video\python.exe')
    )
    return $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}

function Get-StudioLogFile {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [string]$Prefix = 'studio'
    )
    $directory = Join-Path $Root 'local_tmp\logs'
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    return (Join-Path $directory ($Prefix + '-' + (Get-Date -Format 'yyyyMMdd') + '.log'))
}
