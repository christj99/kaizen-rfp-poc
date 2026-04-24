# Bring up the full Kaizen RFP POC stack: Postgres, n8n, FastAPI, Streamlit.
# Idempotent — safe to run multiple times.

. "$PSScriptRoot\_common.ps1"

Write-Host "[demo] checking prerequisites..." -ForegroundColor Cyan
Require-Command docker
Require-Command python

if (-not (Test-Path (Join-Path $RepoRoot '.env'))) {
    throw ".env not found. Copy .env.example to .env and fill in ANTHROPIC_API_KEY first."
}

Import-DotEnv
$py = Get-VenvPython

Write-Host "[demo] starting Docker services (Postgres + n8n)..." -ForegroundColor Cyan
# `docker compose up -d` prints pull/start progress to stderr even on success.
# Under $ErrorActionPreference='Stop' (set in _common.ps1), PowerShell 5.1
# treats each native-stderr line as a terminating error and aborts the script
# before uvicorn/streamlit start. Scope `Continue` narrowly so we still honor
# exit codes below.
Push-Location $RepoRoot
try {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        docker compose up -d 2>&1 | ForEach-Object { Write-Host $_ }
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

Wait-Postgres

Write-Host "[demo] applying DB schema if needed..." -ForegroundColor Cyan
& $py (Join-Path $RepoRoot 'services\api\db\migrate.py')
if ($LASTEXITCODE -ne 0) { throw "migration failed (exit $LASTEXITCODE)" }

# --- FastAPI ---
$apiPort    = Get-EnvOrDefault 'API_PORT' '8000'
$apiHost    = Get-EnvOrDefault 'API_HOST' '0.0.0.0'
$apiPidFile = Join-Path $RepoRoot '.uvicorn.pid'
$apiLog     = Join-Path $LogDir 'api.log'
$apiErr     = Join-Path $LogDir 'api.err.log'

if (Test-PidAlive $apiPidFile) {
    Write-Host "[demo] FastAPI already running (pid $((Get-Content $apiPidFile).Trim()))." -ForegroundColor Yellow
} else {
    Write-Host "[demo] starting FastAPI on :$apiPort..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath $py `
        -ArgumentList @('-m', 'uvicorn', 'services.api.main:app', '--host', $apiHost, '--port', $apiPort) `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $apiLog `
        -RedirectStandardError  $apiErr
    $proc.Id | Out-File -FilePath $apiPidFile -Encoding ascii
}

# --- Streamlit ---
$uiPort    = Get-EnvOrDefault 'STREAMLIT_PORT' '8501'
$uiPidFile = Join-Path $RepoRoot '.streamlit.pid'
$uiLog     = Join-Path $LogDir 'ui.log'
$uiErr     = Join-Path $LogDir 'ui.err.log'

if (Test-PidAlive $uiPidFile) {
    Write-Host "[demo] Streamlit already running (pid $((Get-Content $uiPidFile).Trim()))." -ForegroundColor Yellow
} else {
    Write-Host "[demo] starting Streamlit on :$uiPort..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath $py `
        -ArgumentList @('-m', 'streamlit', 'run', 'services/ui/app.py', '--server.port', $uiPort, '--server.headless', 'true') `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $uiLog `
        -RedirectStandardError  $uiErr
    $proc.Id | Out-File -FilePath $uiPidFile -Encoding ascii
}

Start-Sleep -Seconds 2

$n8nPort = Get-EnvOrDefault 'N8N_PORT' '5678'
$n8nUser = Get-EnvOrDefault 'N8N_BASIC_AUTH_USER' 'admin'

Write-Host ""
Write-Host "Kaizen RFP POC is up." -ForegroundColor Green
Write-Host "  Streamlit UI   http://localhost:$uiPort"    -ForegroundColor Green
Write-Host "  FastAPI docs   http://localhost:$apiPort/docs" -ForegroundColor Green
Write-Host "  n8n            http://localhost:$n8nPort  (user: $n8nUser)" -ForegroundColor Green
Write-Host ""
Write-Host "Logs: logs/api.log  logs/ui.log"
Write-Host "Stop: .\scripts\demo_stop.ps1"
