# Shared helpers for scripts/*.ps1. Dot-source into other scripts.

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LogDir = Join-Path $RepoRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Import-DotEnv {
    # Populate env vars from .env, but never overwrite a value already exported
    # in the current shell. An exported-but-empty value counts as "unset" so
    # .env can fill it in — this matches the behaviour of services/api/_env.py
    # and avoids the classic footgun where a stub .env clobbers a real shell
    # key (e.g. OPENAI_API_KEY=sk-xxxxx placeholder overwriting a live key).
    $envFile = Join-Path $RepoRoot '.env'
    if (-not (Test-Path $envFile)) { return }
    Get-Content $envFile | ForEach-Object {
        $line = $_
        if ($line -match '^\s*#') { return }
        if ($line -match '^\s*$') { return }
        if ($line -match '^\s*([^=\s]+)\s*=\s*(.*)$') {
            $name = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            if ($value.StartsWith('"') -and $value.EndsWith('"')) {
                $value = $value.Substring(1, $value.Length - 2)
            } elseif ($value.StartsWith("'") -and $value.EndsWith("'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $existing = [Environment]::GetEnvironmentVariable($name)
            if ([string]::IsNullOrEmpty($existing)) {
                Set-Item -Path "Env:$name" -Value $value
            }
        }
    }
}

function Get-EnvOrDefault {
    param([string]$Name, [string]$Default)
    $val = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrEmpty($val)) { return $Default }
    return $val
}

function Get-VenvPython {
    $candidates = @(
        (Join-Path $RepoRoot '.venv\Scripts\python.exe'),
        (Join-Path $RepoRoot '.venv\bin\python.exe'),
        (Join-Path $RepoRoot '.venv\bin\python')
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    throw "Python venv not found at .venv/. Create it with: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt"
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "required command not found: $Name"
    }
}

function Wait-Postgres {
    Write-Host "[demo] waiting for Postgres to accept connections..." -ForegroundColor Cyan
    $pgUser = Get-EnvOrDefault 'POSTGRES_USER' 'kaizen'
    $pgDb = Get-EnvOrDefault 'POSTGRES_DB' 'kaizen_rfp'
    for ($i = 0; $i -lt 30; $i++) {
        docker exec kaizen_postgres pg_isready -U $pgUser -d $pgDb *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[demo] Postgres is ready." -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "Postgres did not become ready in time."
}

function Test-PidAlive {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) { return $false }
    $raw = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($raw)) { return $false }
    $procId = 0
    if (-not [int]::TryParse($raw.Trim(), [ref]$procId)) { return $false }
    return [bool](Get-Process -Id $procId -ErrorAction SilentlyContinue)
}
