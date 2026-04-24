# Cleanly stop the Kaizen RFP POC stack.

. "$PSScriptRoot\_common.ps1"

function Stop-PidFile {
    param([string]$PidFile, [string]$Name)
    if (-not (Test-Path $PidFile)) {
        Write-Host "[demo] no $Name pid file at $PidFile" -ForegroundColor Yellow
        return
    }
    $raw = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $procId = 0
    if ($raw -and [int]::TryParse($raw.Trim(), [ref]$procId)) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "[demo] stopping $Name (pid $procId)..." -ForegroundColor Cyan
            try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {}
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Stop-PidFile (Join-Path $RepoRoot '.uvicorn.pid')   'FastAPI'
Stop-PidFile (Join-Path $RepoRoot '.streamlit.pid') 'Streamlit'

Write-Host "[demo] stopping Docker services..." -ForegroundColor Cyan
# docker compose writes status lines to stderr even on success; silence the
# stop-on-error scoping just for this call (see demo_start.ps1 for context).
Push-Location $RepoRoot
try {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        docker compose down 2>&1 | ForEach-Object { Write-Host $_ }
    } finally {
        $ErrorActionPreference = $prevEap
    }
} finally {
    Pop-Location
}

Write-Host "[demo] stopped." -ForegroundColor Green
