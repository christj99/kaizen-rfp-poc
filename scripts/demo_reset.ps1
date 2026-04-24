# Demo "oh no" button: wipe all user data, re-seed past proposals, /health check.
# Target: under 60 seconds end-to-end.

. "$PSScriptRoot\_common.ps1"

Import-DotEnv
$py = Get-VenvPython

# Native executables (python, docker) emit progress to stderr even on success.
# Under $ErrorActionPreference='Stop' (set in _common.ps1) PS 5.1 treats every
# stderr line as a terminating error and aborts the script. Drop to 'Continue'
# for this script — we still honor $LASTEXITCODE for genuine failures.
$ErrorActionPreference = 'Continue'

$start = Get-Date

Write-Host "[demo_reset] stopping Python services..." -ForegroundColor Cyan
foreach ($pidFile in @((Join-Path $RepoRoot '.uvicorn.pid'), (Join-Path $RepoRoot '.streamlit.pid'))) {
    if (Test-Path $pidFile) {
        $raw = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $procId = 0
        if ($raw -and [int]::TryParse($raw.Trim(), [ref]$procId)) {
            try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {}
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

Wait-Postgres

Write-Host "[demo_reset] truncating user tables..." -ForegroundColor Cyan
$truncateScript = @'
from services.api.db.client import db_cursor
with db_cursor() as cur:
    cur.execute("""
        TRUNCATE TABLE
            draft_jobs, drafts, screenings, rfps,
            proposal_chunks, past_proposals,
            audit_log
        RESTART IDENTITY CASCADE
    """)
print("[demo_reset] tables truncated")
'@
$tmp = [System.IO.Path]::GetTempFileName() + '.py'
Set-Content -Path $tmp -Value $truncateScript -Encoding utf8
try {
    Push-Location $RepoRoot
    try { & $py $tmp; if ($LASTEXITCODE -ne 0) { throw "truncate failed (exit $LASTEXITCODE)" } }
    finally { Pop-Location }
} finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }

Write-Host "[demo_reset] re-indexing past proposals..." -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    & $py -m services.api.rag.indexer
    if ($LASTEXITCODE -ne 0) { throw "indexer failed (exit $LASTEXITCODE)" }
} finally { Pop-Location }

# --- restart uvicorn + streamlit ---
$apiPort = Get-EnvOrDefault 'API_PORT' '8000'
$apiHost = Get-EnvOrDefault 'API_HOST' '0.0.0.0'
$uiPort  = Get-EnvOrDefault 'STREAMLIT_PORT' '8501'

Write-Host "[demo_reset] starting FastAPI..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $py `
    -ArgumentList @('-m', 'uvicorn', 'services.api.main:app', '--host', $apiHost, '--port', $apiPort) `
    -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $LogDir 'api.log') `
    -RedirectStandardError  (Join-Path $LogDir 'api.err.log')
$proc.Id | Out-File -FilePath (Join-Path $RepoRoot '.uvicorn.pid') -Encoding ascii

Write-Host "[demo_reset] starting Streamlit..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $py `
    -ArgumentList @('-m', 'streamlit', 'run', 'services/ui/app.py', '--server.port', $uiPort, '--server.headless', 'true') `
    -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $LogDir 'ui.log') `
    -RedirectStandardError  (Join-Path $LogDir 'ui.err.log')
$proc.Id | Out-File -FilePath (Join-Path $RepoRoot '.streamlit.pid') -Encoding ascii

# Poll /health up to 25s — uvicorn cold-start on Windows after a kill cycle
# can take ~10-15s before the socket binds. We want the script's "done" to
# match observable readiness; target budget is still <60s total.
$ready = $false
for ($i = 0; $i -lt 25; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$apiPort/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}

$elapsed = [int]((Get-Date) - $start).TotalSeconds
Write-Host ""
if ($ready) {
    Write-Host "[demo_reset] done in $elapsed s." -ForegroundColor Green
} else {
    Write-Host "[demo_reset] done in $elapsed s, but /health did not come back OK." -ForegroundColor Yellow
}
Write-Host "  UI:  http://localhost:$uiPort"
Write-Host "  API: http://localhost:$apiPort/docs"
